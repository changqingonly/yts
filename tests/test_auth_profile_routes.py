from __future__ import annotations

import base64
import logging
from collections.abc import Iterator

import pytest
from conftest import reset_cached_db_engine
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from fastapi.testclient import TestClient
from yts_server.errors import AppError
from yts_server.main import create_app


@pytest.fixture(autouse=True)
def isolated_sqlite_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "yts-test.db"
    monkeypatch.setenv("YTS_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("YTS_AUTH_JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-tests")

    reset_cached_db_engine()
    yield
    reset_cached_db_engine()


def test_health_still_works_with_error_handlers() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_profile_update_preflight_allows_put_from_frontend_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/user/profile",
            headers={
                "Origin": "http://127.0.0.1:1420",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_cors_preflight_rejection_logs_specific_reason(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="yts_server.cors")

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/user/profile",
            headers={
                "Origin": "http://example.invalid",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 400
    assert "CORS preflight rejected" in caplog.text
    assert "path=/api/user/profile" in caplog.text
    assert "origin=http://example.invalid" in caplog.text
    assert "request_method=PUT" in caplog.text
    assert "failures=origin" in caplog.text


def test_register_key_returns_rsa_oaep_key() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/auth/register_key")

    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "RSA-OAEP-256"
    assert body["key_id"].startswith("rk-")
    assert body["jwk"]["kty"] == "RSA"
    assert body["jwk"]["alg"] == "RSA-OAEP-256"


def test_password_key_can_decrypt_once() -> None:
    from yts_server.security.password_keys import issue_password_key, take_and_decrypt_password

    issued = issue_password_key()
    ciphertext = issued.public_key.encrypt(
        b"Password123",
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    ciphertext_b64 = base64.b64encode(ciphertext).decode("ascii")

    assert take_and_decrypt_password(issued.key_id, ciphertext_b64) == "Password123"
    with pytest.raises(AppError):
        take_and_decrypt_password(issued.key_id, ciphertext_b64)


def test_argon2_hash_verifies_and_rejects_plaintext() -> None:
    from yts_server.security.passwords import hash_password, verify_password

    digest = hash_password("Password123")

    assert digest != "Password123"
    assert verify_password("Password123", digest)
    assert not verify_password("WrongPassword123", digest)


def test_register_login_me_profile_logout_flow() -> None:
    with TestClient(create_app()) as client:
        registered = register_via_test_crypto(client, "me@example.com", "Password123")
        token = registered["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["email"] == "me@example.com"

        profile = client.put(
            "/api/user/profile",
            headers=headers,
            json={
                "username": "rain_writer",
                "avatar_url": None,
                "birthday": "1995-06-01",
                "bio": "写雨和回忆",
                "gender": "unknown",
            },
        )
        assert profile.status_code == 200
        assert profile.json()["username"] == "rain_writer"
        assert profile.json()["bio"] == "写雨和回忆"

        login = login_via_test_crypto(client, "rain_writer", "Password123")
        assert login["email"] == "me@example.com"

        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200

        rejected = client.get("/api/auth/me", headers=headers)
        assert rejected.status_code == 401


def register_via_test_crypto(client: TestClient, email: str, password: str) -> dict:
    key = client.get("/api/auth/register_key").json()
    public_key = public_key_from_jwk(key["jwk"])
    password_ciphertext_b64 = encrypt_password(public_key, password)
    confirm_password_ciphertext_b64 = encrypt_password(public_key, password)
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "key_id": key["key_id"],
            "password_ciphertext_b64": password_ciphertext_b64,
            "confirm_password_ciphertext_b64": confirm_password_ciphertext_b64,
            "agreement_accepted": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def login_via_test_crypto(client: TestClient, account: str, password: str) -> dict:
    key = client.get("/api/auth/login_key").json()
    public_key = public_key_from_jwk(key["jwk"])
    response = client.post(
        "/api/auth/login",
        json={
            "account": account,
            "key_id": key["key_id"],
            "password_ciphertext_b64": encrypt_password(public_key, password),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def public_key_from_jwk(jwk: dict) -> rsa.RSAPublicKey:
    modulus = int.from_bytes(base64.urlsafe_b64decode(_pad_base64(jwk["n"])), "big")
    exponent = int.from_bytes(base64.urlsafe_b64decode(_pad_base64(jwk["e"])), "big")
    return RSAPublicNumbers(exponent, modulus).public_key()


def encrypt_password(public_key: rsa.RSAPublicKey, password: str) -> str:
    ciphertext = public_key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def _pad_base64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return padded.encode("ascii")
