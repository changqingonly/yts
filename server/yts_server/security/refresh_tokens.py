from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_refresh_token(token: str, expected_digest: str) -> bool:
    return hmac.compare_digest(hash_refresh_token(token), expected_digest)
