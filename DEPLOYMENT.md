# Deployment Information

## Public URL
https://day14-production-agent-d0bz.onrender.com

## Platform
Render (Web Service — Docker runtime, Root Directory: `06-lab-complete`, Region: Oregon US West) + Render Key Value (Redis, cùng private network Oregon)

## Test Commands (4 lệnh tự kiểm CP6)

Đặt biến môi trường trước khi chạy (thay `<YOUR_KEY>` bằng `AGENT_API_KEY` đã đặt trên Render Dashboard):

```bash
export BASE="https://day14-production-agent-d0bz.onrender.com"
export AGENT_API_KEY="<YOUR_KEY>"

# 1. Health check (liveness) -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (kiểm tra kết nối Redis trên cloud) -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. POST /ask không có API key -> Expected: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. POST /ask có API key hợp lệ -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

### Kết quả kiểm thử thực tế

- `GET /health` → `HTTP/1.1 200 OK`: `{"status":"ok","environment":"production","uptime_seconds":116.4}`
- `GET /ready` → `HTTP/1.1 200 OK`: `{"status":"ready","environment":"production"}`
- `POST /ask` (không có `X-API-Key`) → `HTTP/1.1 401 Unauthorized`: `{"detail":"Invalid or missing API key"}`
- `POST /ask` (có `X-API-Key` hợp lệ) → `HTTP/1.1 200 OK` *(xem ảnh `screenshots/test.png`)*

## Environment Variables Set (trên Render Dashboard — không ghi giá trị secret trong repo)

- `PORT` *(Render tự động inject, Dockerfile lắng nghe `${PORT:-8000}`)*
- `ENVIRONMENT` (`production`)
- `LOG_LEVEL` (`INFO`)
- `REDIS_URL` *(Internal Key Value URL của service `day14-redis` trên Render)*
- `AGENT_API_KEY` *(Secret đặt trực tiếp trên Render Dashboard)*
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
