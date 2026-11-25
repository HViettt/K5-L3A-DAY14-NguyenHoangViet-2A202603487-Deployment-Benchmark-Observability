"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
App vẫn khởi động được khi Redis chưa sẵn sàng (không ping lúc import).
"""
import redis

from app.config import settings


def _create_client() -> redis.Redis | None:
    if not settings.redis_url:
        return None
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


r: redis.Redis | None = _create_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho GET /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng connection pool khi graceful shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
