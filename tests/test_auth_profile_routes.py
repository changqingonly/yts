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


def test_local_profile_business_routes_bypass_auth_with_stable_local_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YTS_PROFILE", "local")
    with TestClient(create_app()) as client:
        first = client.get("/api/user/profile")
        second = client.get("/api/user/profile")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["username"] == second.json()["username"]


def test_cloud_profile_business_routes_still_require_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YTS_PROFILE", "cloud")
    with TestClient(create_app()) as client:
        response = client.get("/api/user/profile")

    assert response.status_code == 401


def test_health_still_works_with_error_handlers() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_health_exposes_inference_config_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YTS_INFERENCE_BACKEND", "cloud")
    monkeypatch.setenv("YTS_DEEPSEEK_API_KEY", "sk-deepseek-health-secret")
    monkeypatch.setenv("YTS_DEEPSEEK_TEXT_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("YTS_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("YTS_DEEPSEEK_REQUEST_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("YTS_DEEPSEEK_MAX_RETRIES", "1")
    monkeypatch.setenv("YTS_OPENAI_API_KEY", "sk-health-secret")
    monkeypatch.setenv("YTS_OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("YTS_OPENAI_BASE_URL", "https://api.example.test:8088/v1")
    monkeypatch.setenv("YTS_OPENAI_REQUEST_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("YTS_OPENAI_MAX_RETRIES", "0")
    monkeypatch.setenv("YTS_LOGGING_LEVEL", "DEBUG")
    monkeypatch.setenv("YTS_LOGGING_FORMAT", "json")
    monkeypatch.setenv("YTS_GATEWAY_TEXT_MAX_TOKENS", "512")
    monkeypatch.setenv("YTS_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("YTS_IMAGE_MODEL", "gpt-image-1")

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["inference_backend"] == "cloud"
    assert body["openai_text_model"] == "gpt-4.1-mini"
    assert body["default_text_model"]
    assert body["model_fallbacks"]
    assert body["deepseek_text_model"] == "deepseek/deepseek-chat"
    assert body["deepseek_base_url_configured"] is True
    assert body["deepseek_base_url_scheme"] == "https"
    assert body["deepseek_base_url_host"] == "api.deepseek.com"
    assert body["deepseek_base_url_path"] == "/v1"
    assert body["deepseek_request_timeout_seconds"] == 90
    assert body["deepseek_max_retries"] == 1
    assert body["deepseek_api_key_configured"] is True
    assert body["deepseek_api_key_length"] == len("sk-deepseek-health-secret")
    assert body["openai_image_model"] == "gpt-image-1"
    assert body["openai_speech_model"]
    assert body["openai_base_url_configured"] is True
    assert body["openai_base_url_scheme"] == "https"
    assert body["openai_base_url_host"] == "api.example.test"
    assert body["openai_base_url_port"] == 8088
    assert body["openai_base_url_path"] == "/v1"
    assert body["openai_request_timeout_seconds"] == 180
    assert body["openai_max_retries"] == 0
    assert body["openai_api_key_configured"] is True
    assert body["openai_api_key_length"] == len("sk-health-secret")
    assert body["gateway_text_max_tokens"] == 512
    assert body["logging_level"] == "DEBUG"
    assert body["logging_format"] == "json"
    assert body["image_provider"] == "openai"
    assert body["image_model"] == "gpt-image-1"
    assert "sk-health-secret" not in response.text
    assert "sk-deepseek-health-secret" not in response.text


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


def test_profile_update_preflight_allows_packaged_tauri_webview_origin() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/user/profile",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["access-control-allow-origin"] == "tauri://localhost"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_profile_update_preflight_allows_x_yts_client_header() -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/user/profile",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type,x-yts-client",
            },
        )

    assert response.status_code == 200
    assert response.text == "OK"
    assert response.headers["access-control-allow-origin"] == "tauri://localhost"


def test_profile_update_preflight_uses_configured_allowed_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "YTS_SERVER_ALLOWED_ORIGINS",
        '["http://127.0.0.1:1420","https://studio.example.test"]',
    )

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/user/profile",
            headers={
                "Origin": "https://studio.example.test",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://studio.example.test"


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


def test_validation_log_does_not_include_authentication_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "SENSITIVE-CIPHERTEXT-MARKER"
    caplog.set_level(logging.WARNING, logger="yts_server.errors")
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/auth/login",
            json={"key_id": "rk-invalid", "password_ciphertext_b64": marker},
        )

    assert response.status_code == 422
    assert marker not in caplog.text


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


def test_uploaded_avatar_is_served_from_returned_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    avatar_dir = tmp_path / "avatars"
    monkeypatch.setenv("YTS_AVATAR_STORAGE_DIR", str(avatar_dir))

    with TestClient(create_app()) as client:
        registered = register_via_test_crypto(client, "avatar@example.com", "Password123")
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        image_bytes = b"\x89PNG\r\n\x1a\n"
        image_data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

        uploaded = client.post(
            "/api/user/avatar/upload",
            headers=headers,
            json={"image_data_url": image_data_url},
        )

        assert uploaded.status_code == 200
        avatar = client.get(uploaded.json()["avatar_url"])
        assert avatar.status_code == 200
        assert avatar.content == image_bytes
        assert avatar.headers["content-type"] == "image/png"


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
