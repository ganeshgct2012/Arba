"""Password hashing, signed session cookies and SSO state signing."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from fastapi import Response

from app.config import SIGNING_SECRET
from app.utils import utcnow


def signed_sso_state(state: str, verifier: str) -> str:
    payload = f"{state}:{verifier}"
    signature = hmac.new(SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_sso_state(cookie: str | None, state: str) -> str | None:
    if not cookie:
        return None
    try:
        cookie_state, verifier, signature = cookie.split(":", maxsplit=2)
    except ValueError:
        return None
    payload = f"{cookie_state}:{verifier}"
    expected = hmac.new(SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected) or not hmac.compare_digest(cookie_state, state):
        return None
    return verifier


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", maxsplit=1)
        candidate = password_hash(password, bytes.fromhex(salt_hex)).split("$", maxsplit=1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def sign_session(user_id: int, role: str, expires: int) -> str:
    payload = f"{user_id}:{role}:{expires}"
    signature = hmac.new(SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_session(value: str) -> tuple[int, str] | None:
    try:
        user_text, role, expires_text, signature = value.split(":", maxsplit=3)
        payload = f"{user_text}:{role}:{expires_text}"
        expected = hmac.new(SIGNING_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature) or int(expires_text) < int(
            utcnow().timestamp()
        ):
            return None
        return int(user_text), role
    except (ValueError, TypeError):
        return None


def set_session_cookie(response: Response, user_id: int, role: str) -> None:
    expiry = int((utcnow() + timedelta(hours=10)).timestamp())
    response.set_cookie(
        "arba_session",
        sign_session(user_id, role, expiry),
        httponly=True,
        samesite="lax",
        secure=os.getenv("ARBA_COOKIE_SECURE", "0") == "1",
        max_age=10 * 60 * 60,
    )
