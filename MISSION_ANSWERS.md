# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

Phân tích `01-localhost-vs-production/develop/app.py` phát hiện **8 anti-patterns** (vượt yêu cầu tối thiểu 5):

1. **Hardcode secrets trong mã nguồn (dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - *Rủi ro:* Khi push lên Git/GitHub, bí mật bị lộ vĩnh viễn trong lịch sử commit; không thể xoay vòng key (rotate) mà không sửa code và redeploy.
2. **Hardcode cấu hình, không quản lý theo môi trường (dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong code, không đọc từ biến môi trường (vi phạm 12-Factor App — *Config*).
3. **Dùng `print()` thay vì structured logging và làm lộ secret ra log (dòng 33–38):**
   - Dùng `print("[DEBUG] ...")` không có timestamp, log level hay định dạng JSON để hệ thống gom log (Loki/Datadog/ELK) phân tích.
   - Nghiêm trọng nhất là dòng 34: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` in thẳng API key ra stdout/log.
4. **Không có Health Check / Readiness endpoint (dòng 42–43):**
   - `GET /health` trả về `404 Not Found`. Các nền tảng cloud/orchestrator (Railway, Render, Kubernetes) không thể phát hiện app bị treo để tự restart hoặc ngừng định tuyến traffic.
5. **Bind vào `localhost` thay vì `0.0.0.0` (dòng 51):**
   - `host="localhost"` chỉ nhận kết nối loopback nội bộ, nên khi chạy trong Docker container hoặc cloud, traffic từ bên ngoài không thể truy cập được.
6. **Cố định `port=8000` (dòng 52):**
   - Không đọc biến môi trường `PORT` do các nền tảng cloud (Railway, Render, Cloud Run) tự động cấp phát.
7. **Bật `reload=True` mặc định (dòng 53):**
   - File watcher (`WatchFiles`) chạy nền trong production gây tốn CPU/RAM, tăng rủi ro restart ngoài ý muốn và không an toàn.
8. **Không có Graceful Shutdown / Lifecycle management và thiếu kiểm soát input/CORS (dòng 30–31):**
   - Không có `lifespan` hay xử lý `SIGTERM` để hoàn tất các request đang chạy (in-flight requests) trước khi tắt; endpoint `POST /ask` (dòng 30–31) nhận `question` qua query string thay vì JSON body chuẩn, không validate input rỗng và không cấu hình CORS.

---

### Exercise 1.2: Chạy và kiểm thử bản `develop`

Chạy trong Ubuntu WSL2 (`os.name = posix`, `Python 3.14.4`):

```bash
cd 01-localhost-vs-production/develop
python app.py
```

Kết quả kiểm thử bằng `curl -i`:

```http
$ curl -sS -i http://localhost:8000/
HTTP/1.1 200 OK
content-type: application/json

{"message":"Hello! Agent is running on my machine :)"}

$ curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl -sS -i http://localhost:8000/health
HTTP/1.1 404 Not Found
content-type: application/json

{"detail":"Not Found"}
```

Log thực tế từ server `develop` xác nhận rõ anti-pattern lộ secret và bật reload:

```text
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [1904] using WatchFiles
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
INFO:     127.0.0.1:43084 - "GET /health HTTP/1.1" 404 Not Found
```

**Nhận xét:** Ứng dụng chạy được trên máy cá nhân, nhưng hoàn toàn **chưa production-ready** (lộ secret trong code & log, không có `/health`, bind `localhost`, cố định port, bật `reload=True`).

---

### Exercise 1.3: So sánh bản `develop` vs `production`

Chạy bản `01-localhost-vs-production/production/app.py` và kiểm thử thực tế *(header đã được rút gọn)*:

```http
$ curl -sS -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:17:33.525235+00:00"}

$ curl -sS -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true}

$ curl -sS -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}

$ curl -sS -i http://localhost:8000/metrics
HTTP/1.1 200 OK
{"uptime_seconds":0.3,"environment":"development","version":"1.0.0"}
```

**Bảng so sánh `develop` vs `production`:**

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `MAX_TOKENS=500` (dòng 17–22) | Đọc toàn bộ từ env vars qua `Settings` (`config.py` dòng 14–35), có `validate()` fail-fast khi `ENVIRONMENT=production` thiếu `AGENT_API_KEY` (dòng 37–46) | Tách cấu hình khỏi code (12-Factor), không lộ secret lên Git, đổi cấu hình giữa dev/staging/prod không cần sửa code |
| **Network & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (`false` mặc định) (dòng 195–198) | Container/cloud yêu cầu bind `0.0.0.0` và nghe theo biến `PORT`; tắt reload tránh tốn tài nguyên và lỗi ổn định |
| **Health & Readiness** | Không có (`GET /health` → `404`) | Có `/health` (liveness, dòng 135–149), `/ready` (readiness trả `503` khi `not is_ready`, dòng 152–161) và `/metrics` (dòng 164–173) | Giúp orchestrator/load balancer tự restart container chết và chỉ gửi traffic khi app đã sẵn sàng |
| **Logging** | `print()` dạng text tự do, log thẳng `OPENAI_API_KEY` (dòng 33–38) | Structured JSON logging (`logging.basicConfig` dòng 28–32), chỉ log metadata (`question_length`, `client_ip`, `response_length`, dòng 111–122), không log secret | Dễ tìm kiếm/lọc/cảnh báo trong hệ thống log tập trung (Loki, Datadog, ELK) và đảm bảo an toàn dữ liệu nhạy cảm |
| **Shutdown** | Tắt đột ngột, không có cleanup | Dùng FastAPI `lifespan` đặt `is_ready = False` khi tắt (dòng 39–67) + bắt tín hiệu `SIGTERM` (`signal.signal`, dòng 180–189) | Cho phép hoàn tất các request đang xử lý (in-flight) trước khi thoát, tránh lỗi `502`/`504` cho người dùng khi deploy/restart |
| **API Input & CORS** | Nhận `question` qua query string, không validate rỗng, không CORS | Nhận JSON body, validate trống → `422` (dòng 104–108), có `CORSMiddleware` đọc từ `ALLOWED_ORIGINS` (dòng 77–82) | Giao diện API rõ ràng, nhất quán, kiểm soát nguồn gọi từ trình duyệt |

**Ví dụ cụ thể 1 anti-pattern đã được sửa (kèm dòng code):**
- *Anti-pattern:* Hardcode secret & config trong `develop/app.py` (dòng 17–18, 21–22) và lộ secret trong log (dòng 34).
- *Đã sửa trong `production/`:* `config.py` dòng 27, 32 đọc `OPENAI_API_KEY` và `AGENT_API_KEY` bằng `os.getenv(...)`, kiểm tra bắt buộc khi `environment == "production"` ở dòng 42–43; `production/app.py` dòng 111–115 chỉ log `question_length` và `client_ip`, không bao giờ log API key.

---

## Part 2: Docker

### Exercise 2.1: Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - `python:3.11` (dòng 8) — bản phân phối Python đầy đủ (full Debian + toolchain), dung lượng nặng (~1 GB+ trước khi cài thêm package).
2. **Working directory là gì?**
   - `/app` (dòng 11: `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối với thư mục `/app` trong container.
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY` source code?**
   - Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn source code (`app.py`). Khi chỉ sửa code mà không đổi thư viện, Docker dùng lại cache của layer `COPY requirements.txt` và `RUN pip install`, giúp rebuild cực nhanh thay vì phải tải và cài lại toàn bộ dependencies mỗi lần sửa code.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - **`CMD`** (ví dụ dòng 30: `CMD ["python", "app.py"]`) khai báo **lệnh/tham số mặc định** khi container khởi chạy, và **dễ bị ghi đè** nếu truyền lệnh mới lúc `docker run` (vd `docker run my-agent:develop bash`).
   - **`ENTRYPOINT`** khai báo **chương trình thực thi cố định** của container; mọi tham số truyền thêm lúc `docker run` sẽ được nối vào sau `ENTRYPOINT` (chỉ bị ghi đè khi dùng rõ cờ `--entrypoint`). Khi kết hợp cả hai, `ENTRYPOINT` là binary chính còn `CMD` cung cấp các cờ mặc định.

---

### Exercise 2.2: Build và chạy `my-agent:develop`

Build từ **thư mục gốc repo** (theo Lưu ý #4 lớp K5):

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev-test -p 8000:8000 my-agent:develop
```

Kết quả kiểm thử thực tế (lưu ý: `02-docker/develop/app.py` nhận `question` qua query string):

```http
$ curl -sS -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.3,"container":true}

$ curl -sS -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

*(Header phụ đã được rút gọn; container đã được dừng và xóa sau khi test.)*

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`) & So sánh dung lượng

**Phân tích 2 stages trong `02-docker/production/Dockerfile`:**
- **Stage 1 (`builder`, dòng 16–29):** Dùng base `python:3.11-slim`, cài công cụ biên dịch (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`. Stage này **không** được đưa vào image cuối cùng.
- **Stage 2 (`runtime`, dòng 36–72):** Khởi tạo từ `python:3.11-slim` sạch, tạo non-root user `appuser` (dòng 40), chỉ `COPY --from=builder /root/.local /home/appuser/.local` (dòng 45) cùng source code (`main.py`, `utils/mock_llm.py`), chuyển sang `USER appuser` (dòng 58), thêm `HEALTHCHECK` (dòng 68–69) và chạy `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2` (dòng 72).
- **Tại sao image nhỏ hơn?** Vì (1) dùng base `python:3.11-slim` thay vì `python:3.11` full, và (2) toàn bộ trình biên dịch `gcc`, `libpq-dev` cùng các file tạm trong giai đoạn build bị bỏ lại ở stage `builder`, không tồn tại trong image `runtime`.

**So sánh dung lượng đo thực tế bằng `docker images my-agent`:**

```text
REPOSITORY   TAG        SIZE
my-agent     advanced   240MB
my-agent     develop    1.67GB
```

- **Develop (`my-agent:develop`):** `1.67 GB` (`1670 MB`)
- **Production (`my-agent:advanced`):** `240 MB` (đạt yêu cầu `< 500 MB`)
- **Chênh lệch:** Giảm **~85.6%** (`1430 MB`, nhỏ hơn gần 7 lần).

---

### Exercise 2.4: Docker Compose Stack (`02-docker/production/docker-compose.yml`)

**Các service được khởi động (4 services) và cách giao tiếp:**
- Tất cả 4 service chạy chung trong bridge network nội bộ `internal`, giao tiếp qua DNS tên service (`agent`, `redis`, `qdrant`).
- Chỉ **`nginx`** mở cổng ra host (`80:80`, `443:443`), đóng vai trò Reverse Proxy + Load Balancer + thêm security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, ẩn version) + rate limiting (`10r/s`, burst `20`).
- **`agent`** không expose port ra ngoài host, lắng nghe cổng `8000` nội bộ, đợi `redis` và `qdrant` đạt trạng thái `service_healthy` (`depends_on`), được cấu hình biến môi trường kết nối tới `redis://redis:6379/0` và `http://qdrant:6333`.
- **`redis`** (`redis:7-alpine`, port `6379`, volume `redis_data`) dùng cho session cache & rate limiting.
- **`qdrant`** (`qdrant/qdrant:v1.9.0`, port `6333/6334`, volume `qdrant_data`) dùng làm vector database cho RAG.

**Sơ đồ kiến trúc stack:**

```text
                    Host (Client)
                         │  HTTP :80 (port :443 expose chờ TLS cert)
                         ▼
        ┌──────────────────────────────────────────────┐
        │          Docker Network: internal            │
        │                                              │
        │   ┌───────────────────────┐                  │
        │   │  nginx (nginx:alpine) │                  │
        │   │  Reverse Proxy & LB   │                  │
        │   │  Rate limit 10r/s     │                  │
        │   └──────────┬────────────┘                  │
        │              │ proxy_pass http://agent_backend (agent:8000)
        │              ▼                               │
        │   ┌───────────────────────┐                  │
        │   │   agent (FastAPI)     │                  │
        │   │   uvicorn :8000 x2    │                  │
        │   └───┬───────────────┬───┘                  │
        │       │               │                      │
        │  redis://redis:6379   http://qdrant:6333     │
        │       ▼               ▼                      │
        │  ┌─────────┐     ┌──────────┐                │
        │  │  redis  │     │  qdrant  │                │
        │  │ (cache) │     │ (vector) │                │
        │  └────┬────┘     └────┬─────┘                │
        │       ▼               ▼                      │
        │  [redis_data]   [qdrant_data]                │
        └──────────────────────────────────────────────┘
```

**Kết quả chạy thực tế qua Nginx (`docker compose -p k5-day14-docker up -d`):**

```http
$ curl -sS -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.4,"version":"2.0.0","timestamp":"2026-11-25T08:33:03.987586"}

$ curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

*(Header phụ như `Date`, `Content-Length`, `Connection` đã được rút gọn. Sau khi kiểm thử đã dọn sạch stack bằng `docker compose -p k5-day14-docker down -v` và xóa file tạm `.env.local`.)*

---

## Part 3: Cloud Deployment

### Exercise 3.2: Deploy Agent Part 6 lên Render

- **Nền tảng chính:** Render (`06-lab-complete/`, Docker runtime + Render Key Value / Redis)
- **Public URL:** *(Đang chờ deploy lên Render — sẽ điền URL thật sau khi service live)*
- **Thông tin chi tiết & lệnh kiểm thử:** xem [DEPLOYMENT.md](DEPLOYMENT.md)
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Tại sao khác nhau? |
| --- | --- | --- | --- |
| **Định dạng & phạm vi** | TOML ngắn gọn, chỉ cấu hình **1 service** hiện tại (`[build]`, `[deploy]`) | YAML dạng **Infrastructure-as-Code (Blueprint)** mô tả cả **danh sách nhiều services** (`services: [...]`), có thể khai báo cả web + Redis + envVars trong 1 file | Railway ưu tiên thiết lập nhanh từng service trên dashboard/CLI; Render Blueprint cho phép tái tạo toàn bộ stack từ Git |
| **Cách khai báo build** | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile` | Cả hai đều build trực tiếp từ `Dockerfile` multi-stage, nhưng Render cần chỉ rõ loại service (`web`, `worker`, `keyvalue`) |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` | Cùng cơ chế kiểm tra liveness `/health` trước khi chuyển traffic sang bản deploy mới |
| **Quản lý biến môi trường & Secret** | Không khai báo env vars trong `railway.toml`; đặt trực tiếp trên Railway Dashboard hoặc `railway variables set` | Khai báo trực tiếp `envVars` trong `render.yaml`, hỗ trợ `generateValue: true` (tự sinh secret `AGENT_API_KEY`) và `sync: false` (nhắc người dùng nhập `REDIS_URL` trên dashboard, không lưu vào Git) | Giúp khai báo rõ contract biến môi trường ngay trong repo mà vẫn tránh hardcode secret |
| **Restart policy** | Cấu hình rõ `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3` | Quản lý tự động bởi nền tảng Render (không cần mục restart policy trong Blueprint) | Railway cho tùy biến số lần retry; Render tự quản lý vòng đời container theo health check |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên `main` đi qua **4 bước tuần tự** (mỗi bước đợi bước trước qua `waitFor`):
1. **Test (`id: test`):** Chạy container `python:3.11-slim`, cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v` — nếu test fail sẽ dừng pipeline ngay.
2. **Build (`id: build`):** Dùng `gcr.io/cloud-builders/docker` build image gắn 2 tag (`:$COMMIT_SHA` và `:latest`), tận dụng `--cache-from=...:latest` để tăng tốc layer cache.
3. **Push (`id: push`):** Đẩy toàn bộ tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`id: deploy`):** Gọi `gcloud run deploy` triển khai image gắn đúng `:$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình tài nguyên (`1 CPU`, `512Mi RAM`, `min-instances=1` tránh cold start, `max-instances=10`, concurrency `80`), nạp secret an toàn từ **Google Secret Manager** (`--set-secrets` / `secretKeyRef` trong `service.yaml`), kèm `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

**Phân tích mã nguồn:**
- **API key được kiểm tra ở đâu?** Tại hàm dependency `verify_api_key` (dòng 39–54) đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)` (dòng 36) và so sánh với `AGENT_API_KEY` từ biến môi trường (dòng 35), sau đó inject vào `POST /ask` qua `Depends(verify_api_key)` (dòng 70). `/health` và `/` để public.
- **Điều gì xảy ra nếu thiếu hoặc sai key?**
  - Thiếu header `X-API-Key` → **`401 Unauthorized`** (dòng 44–48).
  - Có header nhưng sai giá trị → **`403 Forbidden`** (dòng 49–53). *(Lưu ý: ở Part 6, hợp đồng script chấm yêu cầu cả thiếu và sai key đều trả `401`.)*
- **Làm sao rotate key không downtime?** Hỗ trợ **nhiều key hợp lệ đồng thời** (ví dụ `AGENT_API_KEYS=old_key,new_key` hoặc kiểm tra trong set/Redis) trong giai đoạn chuyển tiếp: (1) thêm `new_key` bên cạnh `old_key`, (2) cập nhật toàn bộ client sang `new_key`, (3) gỡ `old_key` khỏi biến môi trường.

**Kết quả kiểm thử thực tế (`AGENT_API_KEY=secret-key-123 python app.py`):**

```http
# 1) Không có API key -> 401
$ curl -sS -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:43:24 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2) Sai API key -> 403
$ curl -sS -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 08:43:24 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}

# 3) Đúng API key -> 200
$ curl -sS -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:43:24 GMT
server: uvicorn
content-length: 114
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

**Phân tích mã nguồn:**
- **JWT Flow (`auth.py`):** Client gửi username/password tới `POST /auth/token` (`app.py` dòng 105–118) → `authenticate_user` kiểm tra tài khoản (`student`/`demo123` role `user`, `teacher`/`teach456` role `admin`, dòng 27–30) → `create_token` ký JWT bằng `HS256` (`exp` = 60 phút, payload chứa `sub`, `role`, `iat`, `exp`, dòng 35–43). Mọi request tới `/ask` đi qua `verify_token` (`Authorization: Bearer <token>`, dòng 46–67): thiếu hoặc hết hạn → `401`, token không hợp lệ → `403`.
- **Thuật toán Rate Limiting (`rate_limiter.py`):** Docstring ghi *Sliding Window Counter*, nhưng cách cài đặt thực tế là **Sliding Window Log** dùng `collections.deque` lưu timestamp của từng request theo `user_id` (dòng 27) và `popleft()` mọi timestamp cũ hơn `now - window_seconds` (dòng 39–40). Khi `len(window) >= max_requests`, trả về **`429 Too Many Requests`** kèm các header chuẩn `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` (dòng 45–62).
- **Giới hạn & cách xử lý cho Admin:** `rate_limiter_user` giới hạn **10 req / 60 giây**, còn `rate_limiter_admin` giới hạn **100 req / 60 giây** (dòng 86–87). Trong `app.py` dòng 141, hệ thống kiểm tra `role == "admin"` để chọn limiter cao hơn (hoặc nếu muốn bypass hoàn toàn cho admin thì bỏ qua bước `limiter.check()` khi `role == "admin"`).

**Kết quả kiểm thử thực tế (tài khoản `student` / `demo123`, token đã che):**

```http
# 1) Gọi /ask không có token -> 401
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:43:26 GMT
server: uvicorn
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# 2) Lấy token tại POST /auth/token (student / demo123)
Token acquired (masked): eyJhbGciOiJI...<REDACTED>

# 3) Vòng lặp 12 requests với Authorization: Bearer <REDACTED>
>>> Request #1:
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
{"question":"Test 1","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

>>> Request #2..#9 -> HTTP 200 (requests_remaining giảm dần 8..1)

>>> Request #10:
HTTP/1.1 200 OK
{"question":"Test 10","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000179}}

>>> Request #11 (vượt 10 req/phút -> 429):
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 08:43:28 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795596268
retry-after: 59
content-length: 98
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}

>>> Request #12 -> HTTP 429
```

*(Header phụ ở Request #1 và #10 được rút gọn; Request #11 giữ nguyên đầy đủ header trả về từ `curl -i`.)*

---

### Exercise 4.4: Cost Guard — Giải thích thiết kế & Vì sao cần cả Rate Limit lẫn Cost Guard

- **Tại sao cần cả Rate Limit và Cost Guard?**
  - **Rate Limit (`429`)** bảo vệ **tốc độ/tài nguyên hệ thống** (chống spam, DDoS, cạn worker) bằng cách đếm số request/phút.
  - **Cost Guard (`402`)** bảo vệ **ngân sách tiền LLM**. Với AI Agent, một request duy nhất có prompt/output rất dài (hàng chục nghìn token) hoàn toàn lọt qua giới hạn 10 req/phút nhưng vẫn đốt rất nhiều tiền. Do đó phải có cả 2 lớp bảo vệ song song.
- **Cách triển khai trong `04-api-gateway/production/cost_guard.py`:**
  - Tính chi phí dựa trên đơn giá input/output token (`PRICE_PER_1K_INPUT_TOKENS = 0.00015`, `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`, dòng 20–21).
  - Kiểm tra **2 tầng ngân sách** trước khi gọi LLM (`check_budget`, dòng 60–91): vượt ngân sách tổng toàn hệ thống (`$10/ngày`) → `503 Service Unavailable`; vượt ngân sách theo user (`$1/ngày`) → **`402 Payment Required`**; đạt 80% budget → ghi log cảnh báo (`WARNING`).
  - Sau khi gọi LLM xong, gọi `record_usage` (dòng 93–110) cộng dồn token và chi phí.
- **Nâng cấp lên Production với Redis (áp dụng cho Part 6):**
  - Bản `cost_guard.py` mẫu đang lưu trong RAM (`self._records: dict`), sẽ bị mất khi restart hoặc sai lệch khi chạy nhiều instance.
  - Khi đưa vào Redis: dùng key theo chu kỳ như `budget:{user_id}:{YYYY-MM}` (hoặc `YYYY-MM-DD` cho ngân sách ngày), đọc tổng chi phí bằng `GET`, kiểm tra `current + estimated_cost > budget_limit` → trả `402`, sau đó cộng dồn nguyên tử bằng `INCRBYFLOAT` và đặt `EXPIRE` (vd 32 ngày cho tháng hoặc 2 ngày cho ngày) để tự dọn key và tự reset đầu chu kỳ mới.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health / Readiness Probes & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

**Phân tích cơ chế:**
- **Liveness (`/health`, dòng 104–144) vs Readiness (`/ready`, dòng 147–168):**
  - `/health` kiểm tra tiến trình còn sống hay không (trả `status`, `uptime_seconds`, `checks.memory`). Nếu fail → nền tảng **restart container**.
  - `/ready` kiểm tra app đã sẵn sàng nhận traffic chưa (`_is_ready`, dòng 160–164): trả **`503`** khi đang startup, đang shutdown hoặc mất dependency (Redis/DB) để Load Balancer **tạm ngừng chia traffic** vào instance này mà không kill nó.
- **Graceful Shutdown (dòng 41–66, 72–81, 175–199):**
  - Middleware `track_requests` (dòng 72–81) đếm số request đang xử lý (`_in_flight_requests`).
  - Khi nhận `SIGTERM`, Uvicorn gọi phần shutdown của `lifespan` (dòng 54–66): đặt `_is_ready = False`, đợi `_in_flight_requests == 0` (tối đa 30 giây, khớp `timeout_graceful_shutdown=30` ở dòng 198) rồi mới thoát sạch.

**Kết quả kiểm thử thực tế (`05-scaling-reliability/develop/app.py`):**

```http
$ curl -sS -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:53:50.753157+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}

$ curl -sS -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

*(Header phụ đã được rút gọn.)*

Log shutdown khi gửi `kill -TERM`:

```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 15:53:53,989 INFO 🔄 Graceful shutdown initiated...
2026-11-25 15:53:53,989 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [2585]
```

---

### Exercise 5.3: Stateless Design — Vì sao state trong RAM bị hỏng khi scale?

- **Vấn đề của Stateful (lưu trong RAM):** Khi chạy 3 instance phía sau Load Balancer, Request #1 của User A rơi vào `Instance 1` (lưu lịch sử chat trong RAM của `Instance 1`), nhưng Request #2 rơi vào `Instance 2` → `Instance 2` **không có lịch sử** (mất ngữ cảnh). Tương tự, nếu container restart, toàn bộ state trong RAM biến mất.
- **Giải pháp Stateless (`05-scaling-reliability/production/app.py`):**
  - Toàn bộ session và conversation history được lưu tập trung trong **Redis** qua hàm `save_session(..., ttl_seconds=3600)` gọi `_redis.setex(...)` (dòng 59–63) và đọc lại bằng `get` (dòng 68–72), giới hạn tối đa 20 messages/session (dòng 86–87).
  - `/ready` (dòng 208–215) kiểm tra `_redis.ping()`; nếu mất kết nối Redis sẽ trả **`503`**.

---

### Exercise 5.4 & 5.5: Load Balancing (3 Instances + Nginx) & Test Stateless

Chạy theo Lưu ý #7 lớp K5 trong `05-scaling-reliability/production/` (cổng **8080**, endpoint **`POST /chat`**):

```bash
touch .env.local
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
```

**Trạng thái 5 container (`docker compose -p k5-day14-scaling ps`):**
- 3 agent instances (`k5-day14-scaling-agent-1`, `agent-2`, `agent-3`) đều `Up (healthy)` trên port nội bộ `8000/tcp`.
- `k5-day14-scaling-redis-1` (`redis:7-alpine`) `Up (healthy)`.
- `k5-day14-scaling-nginx-1` (`nginx:alpine`) mở `0.0.0.0:8080->80/tcp`, cấu hình `upstream agent_cluster` dùng Docker DNS `127.0.0.11`, `proxy_next_upstream error timeout http_503` (tự động chuyển sang instance khác nếu 1 instance lỗi/503) và gắn header `X-Served-By $upstream_addr`.

**Kết quả thực tế `python test_stateless.py`:**

```text
Session ID: badc4775-1f9d-4397-8452-e236193ad5ff

Request 1: [instance-71a2d5]  Q: What is Docker?
Request 2: [instance-8600a3]  Q: Why do we need containers?
Request 3: [instance-71a2d5]  Q: What is Kubernetes?
Request 4: [instance-d6587a]  Q: How does load balancing work?
Request 5: [instance-8600a3]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-8600a3', 'instance-71a2d5', 'instance-d6587a'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Kiểm chứng Round-Robin qua header `X-Served-By` (6 request `GET http://localhost:8080/health`):**

```text
Req 1: X-Served-By: 172.21.0.3:8000 | instance-d6587a (storage: redis, redis_connected: true)
Req 2: X-Served-By: 172.21.0.4:8000 | instance-8600a3 (storage: redis, redis_connected: true)
Req 3: X-Served-By: 172.21.0.5:8000 | instance-71a2d5 (storage: redis, redis_connected: true)
Req 4: X-Served-By: 172.21.0.3:8000 | instance-d6587a (storage: redis, redis_connected: true)
Req 5: X-Served-By: 172.21.0.4:8000 | instance-8600a3 (storage: redis, redis_connected: true)
Req 6: X-Served-By: 172.21.0.5:8000 | instance-71a2d5 (storage: redis, redis_connected: true)
```

**Giải thích kết quả:** 5 câu hỏi trong cùng một `session_id` được Nginx chia đều sang cả 3 container khác nhau (`instance-71a2d5`, `instance-8600a3`, `instance-d6587a`), nhưng khi truy vấn `/chat/{session_id}/history` vẫn còn đủ **10 messages** (5 user + 5 assistant) vì toàn bộ state được lưu chung trong Redis thay vì RAM cục bộ của từng instance. *(Sau khi test đã dọn sạch stack bằng `docker compose -p k5-day14-scaling down -v` và xóa `.env.local`.)*

---

## Part 6: Final Project — Checklist Deliverable (`check_production_ready.py`)

Chạy đầy đủ có Docker + Redis + `SIGTERM` trong Ubuntu WSL2 (`os.name = posix`) tại `06-lab-complete/`:

```bash
cd 06-lab-complete
python check_production_ready.py
```

Kết quả thực tế (build image `21s`, kích thước image `56 MB`, `docker stop` tắt êm `exit code 0` trong `0.5s`, `17/17` dòng log JSON hợp lệ):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

| Checkpoint | Đã hỏi AI gì | Nhận được gì | Tự sửa & tự kiểm tra thế nào |
| --- | --- | --- | --- |
| **CP0** | Phân tích đề bài Lab 14 (K5) và hỗ trợ kiểm tra/chuẩn bị môi trường WSL2 + Docker | Bản tóm tắt lộ trình CP0–CP8, phát hiện thiếu distro Ubuntu WSL2 trên Windows, hướng dẫn cài Ubuntu WSL2 và tích hợp Docker Desktop | Tự cài Ubuntu WSL2, bật WSL Integration trong Docker Desktop, cài `python3-pip`/`venv`/`curl`; chạy lệnh xác minh `python --version` (`3.14.4`), `os.name` (`posix`), `docker compose version`, `docker run --rm hello-world` đều thành công |
| **CP1** | Phân tích anti-patterns trong `01-localhost-vs-production/develop/app.py`, so sánh với `production/app.py` + `config.py`, soạn mục Part 1 trong `MISSION_ANSWERS.md` | Danh sách 8 anti-patterns kèm số dòng, bảng so sánh develop vs production, kịch bản chạy kiểm thử và 3 góp ý LOW từ vòng review độc lập | Tự chạy thực tế cả `develop/app.py` và `production/app.py` trong Ubuntu WSL2 (`~/lab14-venv`), đối chiếu response HTTP (`200`/`404`) và log thực tế; chỉnh lại số dòng `lifespan` (`39–67`), bổ sung số dòng mục 8 (`30–31`), ghi chú rút gọn header và chuẩn hóa cột AI Log theo review |
| **CP2** | Phân tích `02-docker/` (`develop/Dockerfile`, `production/Dockerfile`, `docker-compose.yml`, `nginx.conf`), soạn Part 2 trong `MISSION_ANSWERS.md` | Giải thích 4 câu hỏi Dockerfile, phân tích 2 stages multi-stage, sơ đồ kiến trúc stack 4 services và kịch bản build/test Docker | Tự build `my-agent:develop` (`1.67GB`) và `my-agent:advanced` (`240MB`) từ gốc repo, đo dung lượng thật bằng `docker images`, chạy test container `develop` và Compose stack qua Nginx (`-p k5-day14-docker`), phát hiện & sửa lỗi race condition 502 khi agent chưa ready bằng vòng lặp `curl -sf` trước khi lấy response `200 OK`, sau đó dọn sạch stack và `.env.local` |
| **CP3** | Phân tích `04-api-gateway/` (`develop` & `production`: `auth.py`, `rate_limiter.py`, `cost_guard.py`), soạn Part 4 trong `MISSION_ANSWERS.md` và cập nhật Study Guide | Phân tích luồng API Key, JWT, Sliding Window Log, Cost Guard (in-memory vs Redis) và kịch bản test `curl -i` | Tự cài `pyjwt` trong `~/lab14-venv`, chạy thực tế `develop/app.py` với `AGENT_API_KEY=secret-key-123` (kiểm chứng `401`/`403`/`200`) rồi tắt server, chạy tiếp `production/app.py` lấy JWT `student`/`demo123` (che token), chạy vòng lặp 12 request chứng minh request #1–#10 trả `200` và #11–#12 trả `429` kèm `Retry-After: 59`, đối chiếu từng dòng code |
| **CP4** | Phân tích `05-scaling-reliability/` (`develop/app.py`, `production/app.py`, `docker-compose.yml`, `nginx.conf`, `test_stateless.py`), soạn Part 5 trong `MISSION_ANSWERS.md` và cập nhật Study Guide | Phân tích Liveness/Readiness, Graceful Shutdown, Stateless với Redis, Nginx Load Balancer (`proxy_next_upstream`) | Tự chạy thực tế `develop/app.py` kiểm chứng `/health`, `/ready`, `SIGTERM` shutdown; chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3`, chạy `test_stateless.py` chứng minh 5 request đi qua cả 3 instance mà vẫn giữ đủ 10 messages trong Redis, test thêm 6 request `/health` xác nhận Round-Robin qua header `X-Served-By`, rồi `down -v` và xóa `.env.local` |
| **CP5** | Hoàn thiện toàn bộ `TODO` trong `06-lab-complete/` (`app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) theo hợp đồng 12 tiêu chí và cập nhật Study Guide CP5 | Mã nguồn FastAPI production-ready (12-Factor config, `hmac.compare_digest` auth `401`, Redis ZSET sliding window rate limiter `429`, Redis daily/monthly cost guard `402`, custom `JsonFormatter`, `lifespan` graceful shutdown, multi-stage Dockerfile `exec uvicorn`) | Tự chạy `python check_production_ready.py` bản đầy đủ (có Docker, Redis, `uvicorn --workers 2`, `SIGTERM`) trong Ubuntu WSL2 đạt **`PASS 12/12` (`43/43 checks passed`)**, image `56 MB`, `docker stop` `0.5s`, và dán Checklist Deliverable vào `MISSION_ANSWERS.md` |
| **CP7** | Phân tích kết quả load test (`load_test.py`) và eval (`eval/run_eval.py`), xác định 2 câu thiếu trong `KNOWLEDGE_BASE`, điền mục 1–3 `BENCHMARK_REPORT.md` và cập nhật Study Guide CP7 | Phân tích điểm bão hòa concurrency, tail latency (`p95`/`p99` vs `avg`), 2 entry KB cho `security-02` (JWT) và `scaling-03` (HPA), cấu hình CI exit code gate | Tự chạy toàn bộ 10 lệnh benchmark/eval thật trong Ubuntu WSL2 xuất 10 file JSON trong `reports/`, sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` & `production/utils/mock_llm.py` (không sửa `golden_dataset.jsonl`), chạy lại eval đạt **23/23 (100%) PASS, 0 regression**, đối chiếu từng con số trong `BENCHMARK_REPORT.md` khớp 100% file JSON |
