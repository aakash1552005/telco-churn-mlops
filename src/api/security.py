"""API Key Authentication Module.

Enforces Master Contract Section 11 security baseline.
"""

from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

API_KEY_HEADER_NAME: str = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """Validate incoming X-API-Key request header against configured secret keys.

    Args:
        api_key: API Key string extracted from X-API-Key header.

    Returns:
        Validated API key string.

    Raises:
        HTTPException 401: If API key is missing or invalid.
    """
    settings = get_settings()
    valid_keys = settings.API_SECRET_KEYS

    if not api_key:
        logger.warning("Authentication failure: Missing X-API-Key header in request.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key not in valid_keys:
        logger.warning("Authentication failure: Invalid X-API-Key header provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
