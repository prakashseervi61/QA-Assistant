"""Tests for JWT-style auth helpers."""

from unittest.mock import MagicMock, patch

import pytest


class TestTokenCreation:
    def test_token_roundtrip(self):
        """Created token decodes back to the subject."""
        from src.infrastructure.auth.jwt_auth import (
            create_access_token,
            decode_access_token,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SECRET_KEY = "test-secret-key"
            settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60
            mock_settings.return_value = settings

            token = create_access_token("user-123")
            assert decode_access_token(token) == "user-123"

    def test_token_expired(self):
        """Expired token returns None."""
        from src.infrastructure.auth.jwt_auth import (
            create_access_token,
            decode_access_token,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SECRET_KEY = "test-secret-key"
            settings.ACCESS_TOKEN_EXPIRE_MINUTES = -1  # already expired
            mock_settings.return_value = settings

            token = create_access_token("user-123")
            assert decode_access_token(token) is None

    def test_tampered_token_rejected(self):
        """Token with modified payload is rejected."""
        from src.infrastructure.auth.jwt_auth import (
            create_access_token,
            decode_access_token,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SECRET_KEY = "test-secret-key"
            settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60
            mock_settings.return_value = settings

            token = create_access_token("user-123")
            # Tamper with the payload section
            parts = token.split(".")
            parts[1] = "bm90LXZhbGlk"  # base64 of "not-valid" (may need padding)
            tampered = ".".join(parts)
            assert decode_access_token(tampered) is None

    def test_token_with_non_hs256_alg_rejected(self):
        """A token whose header declares alg != HS256 is rejected."""
        import json

        from src.infrastructure.auth.jwt_auth import (
            _b64url_encode,
            decode_access_token,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SECRET_KEY = "test-secret-key"
            mock_settings.return_value = settings

            # Craft a token with an "alg": "none" header (the classic
            # algorithm-confusion attack) but a valid-looking payload.
            header = _b64url_encode(
                json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            payload = _b64url_encode(
                json.dumps(
                    {"sub": "user-123", "iat": 0, "exp": 9999999999},
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            token = f"{header}.{payload}.AAAA"
            assert decode_access_token(token) is None

    def test_token_with_missing_alg_header_rejected(self):
        """A token with no alg claim in the header is rejected."""
        import json

        from src.infrastructure.auth.jwt_auth import (
            _b64url_encode,
            decode_access_token,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.SECRET_KEY = "test-secret-key"
            mock_settings.return_value = settings

            header = _b64url_encode(
                json.dumps({"typ": "JWT"}, separators=(",", ":")).encode("utf-8")
            )
            payload = _b64url_encode(
                json.dumps(
                    {"sub": "user-123", "iat": 0, "exp": 9999999999},
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            token = f"{header}.{payload}.AAAA"
            assert decode_access_token(token) is None


class TestPasswordHashing:
    def test_hash_verify_roundtrip(self):
        """Hashed password verifies correctly."""
        from src.infrastructure.auth.jwt_auth import hash_password, verify_password

        hashed = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", hashed) is True
        assert verify_password("wrong password", hashed) is False

    def test_unique_salts(self):
        """Same password hashes differently due to salt."""
        from src.infrastructure.auth.jwt_auth import hash_password

        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2


class TestAuthDependency:
    def test_dependency_passes_when_auth_disabled(self):
        """Auth disabled -> dependency returns without error."""
        from src.infrastructure.auth.jwt_auth import get_current_user_dependency

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.ENABLE_AUTH = False
            mock_settings.return_value = settings

            import asyncio

            result = asyncio.run(get_current_user_dependency())
            assert result is None

    @pytest.mark.asyncio
    async def test_dependency_rejects_missing_token_when_auth_enabled(self):
        """Auth enabled + no Authorization header -> 401."""
        from fastapi import HTTPException

        from src.infrastructure.auth.jwt_auth import get_current_user_dependency

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.ENABLE_AUTH = True
            settings.SECRET_KEY = "test-secret-key"
            mock_settings.return_value = settings

            class FakeRequest:
                headers = {}  # no Authorization

            with pytest.raises(HTTPException) as excinfo:
                await get_current_user_dependency(request=FakeRequest())
            assert excinfo.value.status_code == 401

    @pytest.mark.asyncio
    async def test_dependency_accepts_valid_token_when_auth_enabled(self):
        """Auth enabled + valid token -> subject returned."""
        from src.infrastructure.auth.jwt_auth import (
            create_access_token,
            get_current_user_dependency,
        )

        with patch("src.infrastructure.auth.jwt_auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.ENABLE_AUTH = True
            settings.SECRET_KEY = "test-secret-key"
            settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60
            mock_settings.return_value = settings

            token = create_access_token("user-123")

            class FakeRequest:
                headers = {"Authorization": f"Bearer {token}"}

            subject = await get_current_user_dependency(request=FakeRequest())
            assert subject == "user-123"
