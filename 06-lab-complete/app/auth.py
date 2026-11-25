"""
API Key authentication — kiểm tra header X-API-Key.
Thiếu hoặc sai key → HTTP 401.
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency cho FastAPI — dùng trong /ask: Depends(verify_api_key)."""
    expected_key = settings.agent_api_key
    if (
        not expected_key
        or not api_key
        or not hmac.compare_digest(api_key.encode("utf-8"), expected_key.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )
    return api_key
