"""Authentication API routes: API key → JWT token exchange."""

import hmac
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.infrastructure.auth.jwt_auth import create_access_token
from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenRequest(BaseModel):
    """Request body for POST /api/auth/token."""

    api_key: str = Field(..., min_length=1, description="API key to exchange")


class TokenResponse(BaseModel):
    """JWT access token returned by POST /api/auth/token."""

    access_token: str
    token_type: str
    expires_in: int


@router.post("/auth/token", response_model=TokenResponse)
async def create_token(request: TokenRequest) -> TokenResponse:
    """Exchange an API key for a short-lived JWT access token.

    The configured ``AUTH_API_KEY`` is compared in constant time. When the
    setting is empty (the default) or the key does not match, the request
    is rejected with 401 so no timing side channel leaks the expected key.
    """
    settings = get_settings()
    expected = settings.AUTH_API_KEY
    if not expected or not hmac.compare_digest(
        request.api_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return TokenResponse(
        access_token=create_access_token(subject="api-client"),
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
