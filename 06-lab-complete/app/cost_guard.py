"""
Cost guard — Theo dõi chi phí LLM theo ngày và tháng trong Redis.
Tổng chi phí vượt DAILY_BUDGET_USD hoặc MONTHLY_BUDGET_USD → HTTP 402.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 2 * 24 * 3600
MONTHLY_TTL_SECONDS = 32 * 24 * 3600


def _cost_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable")

    daily_key, monthly_key = _cost_keys()
    try:
        daily_raw, monthly_raw = r.mget(daily_key, monthly_key)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable") from exc

    daily_spent = float(daily_raw or 0.0)
    monthly_spent = float(monthly_raw or 0.0)

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="LLM budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào Redis và trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is None:
        return cost

    daily_key, monthly_key = _cost_keys()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, DAILY_TTL_SECONDS)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
        pipe.execute()
    except RedisError:
        pass
    return cost
