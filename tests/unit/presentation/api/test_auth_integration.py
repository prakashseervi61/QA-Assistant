"""Integration tests: auth on/off behavior of the FastAPI app."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.infrastructure.config.settings import Settings


def _make_settings(tmp_path, **overrides) -> Settings:
    """Build test settings with safe, deterministic values."""
    defaults = {
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "test-key",
        "EMBEDDING_PROVIDER": "gemini",
        "CHROMA_PERSIST_DIR": str(tmp_path / "chroma"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_app_works_without_auth(tmp_path):
    """With default settings (auth off), endpoints work."""
    from src.presentation.api.app import create_app

    app = create_app(_make_settings(tmp_path))
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_protected_routes_reject_missing_token_when_auth_enabled(tmp_path):
    """Auth enabled + no token -> protected routes return 401, health stays open."""
    from src.infrastructure.auth import jwt_auth
    from src.infrastructure.ratelimit import limiter
    from src.presentation.api.app import create_app

    settings = _make_settings(tmp_path, ENABLE_AUTH=True, SECRET_KEY="test-secret-key")
    with (
        patch.object(jwt_auth, "get_settings", return_value=settings),
        patch.object(limiter, "get_settings", return_value=settings),
    ):
        app = create_app(settings)
        client = TestClient(app)

        # Health is not protected (liveness probes must stay public).
        assert client.get("/api/health").status_code == 200
        # Protected routers require a valid token.
        assert client.get("/api/conversations").status_code == 401
        assert client.get("/api/usage").status_code == 401


def test_protected_routes_accept_valid_token_when_auth_enabled(tmp_path):
    """Auth enabled + valid token -> protected routes work."""
    from src.infrastructure.auth import jwt_auth
    from src.infrastructure.ratelimit import limiter
    from src.presentation.api.app import create_app

    settings = _make_settings(
        tmp_path,
        ENABLE_AUTH=True,
        SECRET_KEY="test-secret-key",
        ACCESS_TOKEN_EXPIRE_MINUTES=60,
    )
    with (
        patch.object(jwt_auth, "get_settings", return_value=settings),
        patch.object(limiter, "get_settings", return_value=settings),
    ):
        token = jwt_auth.create_access_token("user-123")
        app = create_app(settings)
        client = TestClient(app)

        resp = client.get(
            "/api/conversations", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200


class TestTokenEndpoint:
    """POST /api/auth/token exchanges a valid API key for a JWT."""

    def test_valid_api_key_returns_token(self, tmp_path):
        """Valid AUTH_API_KEY -> 200 with a decodable bearer token."""
        from src.infrastructure.auth import jwt_auth
        from src.infrastructure.ratelimit import limiter
        from src.presentation.api.app import create_app
        from src.presentation.api.routes import auth as auth_routes

        settings = _make_settings(
            tmp_path,
            ENABLE_AUTH=True,
            SECRET_KEY="test-secret-key",
            AUTH_API_KEY="test-api-key",
            ACCESS_TOKEN_EXPIRE_MINUTES=60,
        )
        with (
            patch.object(jwt_auth, "get_settings", return_value=settings),
            patch.object(limiter, "get_settings", return_value=settings),
            patch.object(auth_routes, "get_settings", return_value=settings),
        ):
            app = create_app(settings)
            client = TestClient(app)
            resp = client.post("/api/auth/token", json={"api_key": "test-api-key"})

            assert resp.status_code == 200
            body = resp.json()
            assert body["token_type"] == "bearer"
            assert body["expires_in"] == 60 * 60
            # The returned token decodes to the fixed api-client subject.
            assert jwt_auth.decode_access_token(body["access_token"]) == "api-client"

    def test_invalid_api_key_returns_401(self, tmp_path):
        """Wrong key -> 401, no token issued."""
        from src.infrastructure.auth import jwt_auth
        from src.infrastructure.ratelimit import limiter
        from src.presentation.api.app import create_app
        from src.presentation.api.routes import auth as auth_routes

        settings = _make_settings(
            tmp_path,
            ENABLE_AUTH=True,
            SECRET_KEY="test-secret-key",
            AUTH_API_KEY="test-api-key",
        )
        with (
            patch.object(jwt_auth, "get_settings", return_value=settings),
            patch.object(limiter, "get_settings", return_value=settings),
            patch.object(auth_routes, "get_settings", return_value=settings),
        ):
            app = create_app(settings)
            client = TestClient(app)
            resp = client.post("/api/auth/token", json={"api_key": "wrong-key"})

            assert resp.status_code == 401

    def test_default_empty_api_key_returns_401(self, tmp_path):
        """AUTH_API_KEY unset (default) -> every key is rejected."""
        from src.infrastructure.auth import jwt_auth
        from src.infrastructure.ratelimit import limiter
        from src.presentation.api.app import create_app
        from src.presentation.api.routes import auth as auth_routes

        settings = _make_settings(
            tmp_path,
            ENABLE_AUTH=True,
            SECRET_KEY="test-secret-key",
        )  # AUTH_API_KEY left at its empty default
        with (
            patch.object(jwt_auth, "get_settings", return_value=settings),
            patch.object(limiter, "get_settings", return_value=settings),
            patch.object(auth_routes, "get_settings", return_value=settings),
        ):
            app = create_app(settings)
            client = TestClient(app)
            resp = client.post("/api/auth/token", json={"api_key": "anything"})

            assert resp.status_code == 401
