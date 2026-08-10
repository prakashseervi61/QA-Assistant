"""JWT-style authentication helpers built on the standard library.

Tokens are JWT-shaped (``header.payload.signature``) but signed with
HMAC-SHA256 via :mod:`hmac`/:mod:`hashlib` — no third-party JWT library is
required. Passwords are hashed with PBKDF2-HMAC-SHA256.

All auth behaviour is gated by ``settings.ENABLE_AUTH`` (off by default),
so when auth is disabled every dependency here is a no-op.
"""

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import HTTPException, Request

from src.infrastructure.config.settings import get_settings

_PBKDF2_ITERATIONS = 100_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_DIGEST = "sha256"

_JWT_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64url_encode(data: bytes) -> str:
    """Encode bytes as unpadded base64url (RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes | None:
    """Decode unpadded base64url back to bytes, or None if malformed."""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded)
    except (ValueError, TypeError):
        return None


def _sign(body: str, secret: str) -> str:
    """Compute the HMAC-SHA256 signature for a token body."""
    digest = hmac.new(
        secret.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed JWT-shaped token for the given subject.

    Args:
        subject: The user/entity identifier stored in the ``sub`` claim.
        expires_minutes: Token lifetime in minutes. Defaults to
            ``settings.ACCESS_TOKEN_EXPIRE_MINUTES``.

    Returns:
        A compact ``header.payload.signature`` token (HMAC-SHA256).
    """
    settings = get_settings()
    if expires_minutes is None:
        expires_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = int(time.time())

    header = _b64url_encode(
        json.dumps(_JWT_HEADER, separators=(",", ":")).encode("utf-8")
    )
    payload = _b64url_encode(
        json.dumps(
            {"sub": subject, "iat": now, "exp": now + expires_minutes * 60},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    body = f"{header}.{payload}"
    return f"{body}.{_sign(body, settings.SECRET_KEY)}"


def decode_access_token(token: str) -> str | None:
    """Return the token subject, or None if invalid/expired/tampered.

    Every failure path (wrong structure, bad encoding, bad JSON, wrong
    signature, expired claims, non-string subject) returns None so callers
    can treat any failure as "not authenticated".
    """
    if not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, signature_b64 = parts
    if not (header_b64.isascii() and payload_b64.isascii() and signature_b64.isascii()):
        return None

    # Pin the algorithm from the (still unverified) header: tokens that
    # declare anything other than HS256 must be rejected outright, before
    # any signature work happens. Never trust a claim about the algorithm
    # from anywhere else in the token.
    header_bytes = _b64url_decode(header_b64)
    if header_bytes is None:
        return None
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if header.get("alg") != "HS256":
        return None

    settings = get_settings()
    body = f"{header_b64}.{payload_b64}"
    if not hmac.compare_digest(signature_b64, _sign(body, settings.SECRET_KEY)):
        return None

    payload_bytes = _b64url_decode(payload_b64)
    if payload_bytes is None:
        return None
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

    subject = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not isinstance(expires_at, (int, float)):
        return None
    if expires_at < time.time():
        return None
    return subject


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt.

    Returns:
        A string in the format ``pbkdf2$iterations$salt$hash`` where both
        salt and hash are base64-encoded.
    """
    salt = os.urandom(_PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_DIGEST,
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return "pbkdf2${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a ``pbkdf2$...`` hash string.

    Returns:
        True if the password matches, False on mismatch or malformed hash.
    """
    try:
        scheme, iterations_str, salt_b64, hash_b64 = hashed.split("$", 3)
        if scheme != "pbkdf2":
            return False
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_DIGEST,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(derived, expected)


async def get_current_user_dependency(request: Request = None) -> str | None:
    """FastAPI dependency resolving the authenticated subject.

    When ``ENABLE_AUTH`` is False (the default) this is a no-op that returns
    None, so existing endpoints behave exactly as before. When enabled, a
    valid ``Authorization: Bearer <token>`` header is required and a
    missing/invalid token raises ``HTTPException(401)``.

    Note: the ``Request`` parameter carries a default of None so the
    dependency can be invoked directly (e.g. in tests); FastAPI still
    injects the real request because the annotation is exactly ``Request``.

    Returns:
        The token subject when authenticated, else None when auth is off.
    """
    settings = get_settings()
    if not settings.ENABLE_AUTH:
        return None

    authorization = (
        request.headers.get("Authorization") if request is not None else None
    )
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header. Expected 'Bearer <token>'.",
        )

    subject = decode_access_token(token.strip())
    if subject is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return subject
