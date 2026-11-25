"""
Rate limiting — Redis Sorted Set sliding window (60 giây) theo API key.
Vượt RATE_LIMIT_PER_MINUTE → HTTP 429 kèm Retry-After.
"""
import hashlib
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def _rate_limit_key(api_key: str) -> str:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"rate_limit:{key_hash}"


def check_rate_limit(key: str) -> None:
    """Kiểm tra rate limit sliding window trong Redis."""
    if r is None:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")

    limit = settings.rate_limit_per_minute
    redis_key = _rate_limit_key(key)
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            else:
                retry_after = WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter backend unavailable") from exc
