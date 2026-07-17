from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..errors import AppError

_hasher = PasswordHasher()


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise AppError.bad_request("password_too_short", "password too short", "password")
    if len(password) > 200:
        raise AppError.bad_request("password_too_long", "password too long", "password")
    if not any(char.isascii() and char.isalpha() for char in password):
        raise AppError.bad_request(
            "password_letter_required", "password must contain at least one letter", "password"
        )
    if not any(char.isdigit() for char in password):
        raise AppError.bad_request(
            "password_digit_required", "password must contain at least one digit", "password"
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def verify_and_update_password(
    password: str, password_hash: str, *, time_cost: int | None = None
) -> tuple[bool, str | None]:
    hasher = _hasher if time_cost is None else PasswordHasher(time_cost=time_cost)
    try:
        hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False, None
    replacement = hasher.hash(password) if hasher.check_needs_rehash(password_hash) else None
    return True, replacement
