from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from threading import Lock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from ..errors import AppError

KEY_TTL_SECONDS = 5 * 60
RSA_BITS = 2048
MAX_CACHED_KEYS = 256


@dataclass(frozen=True)
class IssuedPasswordKey:
    key_id: str
    jwk: dict
    public_key: RSAPublicKey


@dataclass
class _CachedKey:
    created_at: float
    private_key: RSAPrivateKey


_cache: dict[str, _CachedKey] = {}
_lock = Lock()


def issue_password_key() -> IssuedPasswordKey:
    with _lock:
        _purge_expired_locked()
        if len(_cache) >= MAX_CACHED_KEYS:
            raise AppError.too_many_requests("password key capacity exhausted")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    public_key = private_key.public_key()
    numbers = public_key.public_numbers()
    key_id = f"rk-{uuid.uuid4().hex}"
    jwk = {
        "kty": "RSA",
        "alg": "RSA-OAEP-256",
        "use": "enc",
        "key_ops": ["encrypt"],
        "ext": True,
        "n": _to_base64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _to_base64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }
    with _lock:
        if len(_cache) >= MAX_CACHED_KEYS:
            raise AppError.too_many_requests("password key capacity exhausted")
        _cache[key_id] = _CachedKey(created_at=time.monotonic(), private_key=private_key)
    return IssuedPasswordKey(key_id=key_id, jwk=jwk, public_key=public_key)


def take_and_decrypt_password(key_id: str, ciphertext_b64: str) -> str:
    return take_and_decrypt_passwords(key_id, ciphertext_b64)[0]


def take_and_decrypt_passwords(key_id: str, *ciphertexts_b64: str) -> list[str]:
    key_id = key_id.strip()
    if not key_id:
        raise AppError.bad_request("password_key_required", "key_id is required", "key_id")
    with _lock:
        _purge_expired_locked()
        cached = _cache.pop(key_id, None)
    if cached is None:
        raise AppError.bad_request(
            "password_key_expired", "password key expired or not found", "key_id"
        )
    return [
        _decrypt_with_private_key(cached.private_key, ciphertext_b64)
        for ciphertext_b64 in ciphertexts_b64
    ]


def _decrypt_with_private_key(private_key: RSAPrivateKey, ciphertext_b64: str) -> str:
    try:
        ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise AppError.bad_request(
            "password_ciphertext_invalid", f"invalid password ciphertext: {exc}", "password"
        ) from exc
    try:
        plaintext = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:
        raise AppError.bad_request(
            "password_decrypt_failed", f"decrypt failed: {exc}", "password"
        ) from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError.bad_request(
            "password_utf8_invalid", "decrypted password is invalid utf-8"
        ) from exc


def _purge_expired_locked() -> None:
    now = time.monotonic()
    expired = [key for key, value in _cache.items() if now - value.created_at > KEY_TTL_SECONDS]
    for key in expired:
        del _cache[key]


def _to_base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
