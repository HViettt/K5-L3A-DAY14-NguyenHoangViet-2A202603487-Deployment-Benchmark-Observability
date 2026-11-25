# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file JSON trong `reports/`, CSV trong `benchmark-results/` và screenshot thật trong `screenshots/`.

**Họ tên:** Nguyen Hoang Viet — MSSV: 2A202603487
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + Ubuntu WSL2 (`Python 3.14.4`, `os.name = posix`), Docker Desktop `29.1.3` / Compose `v2.40.3`

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Khớp ngưỡng SLO mặc định của `load_test.py` (`≤ 500ms`); với agent mock có base latency ~120ms + jitter 60ms + retrieval 20ms (~200ms bình thường), ngưỡng 500ms cho phép 95% request phản hồi mượt và phát hiện sớm tình trạng nghẽn hàng đợi hoặc tăng tail latency |
| Error rate `/ask` | < 2.0 % | Khớp ngưỡng SLO mặc định của `load_test.py` (`≤ 2.0%`); `MOCK_ERROR_RATE` mặc định là 1%, nên ngưỡng 2% cho phép dao động thống kê nhỏ nhưng báo động ngay khi upstream lỗi nặng |
| Accuracy trên golden dataset | ≥ 90 % *(mục tiêu sau sửa KB: 100%)* | Với 23 câu hỏi kiến thức lõi, mức ≥ 80–90% là ngưỡng tối thiểu để release và 100% (23/23, 0 regression) là mục tiêu quality gate sau khi bổ sung Knowledge Base |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency "$c" --out "reports/load_v2_c${c}.json"`:

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.64 | 196.3 | 227.2 | 1705.3 | 0.67% | PASS |
| 10 | 34.90 | 196.7 | 331.2 | 1706.3 | 1.67% | PASS |
| 50 | 66.79 | 320.0 | 1534.6 | 2312.7 | 1.67% | FAIL (p95 > 500ms) |
| 100 | 53.84 | 644.8 | 3519.7 | 3936.9 | 0.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency:
- Từ `c=1 → c=10`: RPS tăng gần tuyến tính (`4.64 → 34.90 req/s`), `p50` gần như giữ nguyên (`196.3 → 196.7ms`) vì hệ thống còn dư năng lực xử lý.
- Từ `c=10 → c=50`: RPS chỉ tăng chưa tới gấp đôi (`34.90 → 66.79 req/s`), trong khi `p95` vọt lên `1534.6ms` (vi phạm SLO `500ms`) do bắt đầu xuất hiện xếp hàng (queuing) trên 1 worker/event loop + giới hạn tài nguyên xử lý đồng thời.
- Từ `c=50 → c=100`: Hệ thống vượt điểm bão hòa (saturation knee) — **RPS giảm ngược** từ `66.79` xuống `53.84 req/s`, còn `p50` tăng gấp đôi (`644.8ms`) và `p95` tăng lên `3519.7ms` (gấp ~15.5 lần so với `c=1`).

### 2.2 Tail latency

Chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out "reports/load_v2_slow_${rate}.json"`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 218.0 | 279.6 | 328.8 |
| 0.03 (mặc định) | 249.2 | 300.4 | 1693.5 |
| 0.1 | 342.0 | 1693.3 | 1750.3 |

**Nhận xét:**
- **Chỉ số nhạy nhất với request chậm là `p99` (và tiếp theo là `p95`):** Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm), `avg` chỉ nhích nhẹ `+14.3%` (`218.0 → 249.2ms`), nhưng **`p99` nhảy vọt gấp 5.15 lần** (`328.8 → 1693.5ms`). Khi tăng lên `0.1` (10% request chậm > 5%), tới lượt **`p95` bùng nổ gấp 5.64 lần** (`300.4 → 1693.3ms`, làm trượt SLO), trong khi `avg` vẫn chỉ là `342.0ms` (trông tưởng như đạt `< 500ms`!).
- **Vì sao SLO không nên đặt theo average:** Giá trị trung bình bị "làm phẳng" bởi 90–97% request nhanh nên **che giấu hoàn toàn tail latency**. Trong thực tế, nếu 1 trang web hay 1 agent workflow gọi nhiều bước nối tiếp, chỉ cần 5–10% request chậm gần 2 giây là trải nghiệm người dùng đã rất tệ. Do đó SLO phải đặt theo **p95 hoặc p99**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.00% (23/23) |
| Avg tokens / câu | 57.1 | 109.0 | 116.1 |
| Tổng cost (USD) | $0.000404 | $0.000759 | $0.000812 |
| Cost / câu đúng (USD) | $0.00040395 | $0.00003616 | $0.00003530 |
| Quality gate | FAIL | PASS (≥ 80%) | PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung entry `(["jwt", "json web token"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT là token stateless có thời gian hết hạn (`exp`) và chữ ký số (`signature`), khác với API key |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung entry `(["hpa", "kubernetes"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và `production/utils/mock_llm.py`) giải thích Kubernetes HPA scale pod dựa trên CPU, memory và custom metrics |

*(Không sửa `eval/golden_dataset.jsonl` theo đúng quy định `RULES.md`.)*

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 (có retrieval/RAG) nâng accuracy từ `4.35%` lên `91.30%`, và sau khi bổ sung 2 entry KB lên **`100.00%` (23/23)**, không gây regression nào (`0 regression`).
- **Latency:** v2 có thêm bước `search_knowledge_base` (~20ms) và prompt dài hơn nên `p95` eval tăng nhẹ từ `189.5ms` (v1) lên `212.6ms` (v2) / `215.4ms` (v2 fixed) — mức đánh đổi ~25ms hoàn toàn xứng đáng.
- **Chi phí (`cost / câu đúng` tốt hơn `cost / câu`):** Tổng cost của v2 fixed (`$0.000812`) gần gấp đôi v1 (`$0.000404`) vì prompt chứa thêm context (`116.1` vs `57.1` tokens/câu). Nhưng xét theo **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`)**, v2 fixed chỉ tốn **`$0.00003530`**, **rẻ hơn v1 (`$0.00040395`) tới ~11.4 lần**! Nếu chỉ nhìn `cost / câu`, ta dễ chọn nhầm model rẻ mà trả lời sai hàng loạt.

**Cách dùng exit code của `run_eval.py` làm Quality Gate chặn merge trong CI/CD:**
- `eval/run_eval.py` trả về **exit code `0`** khi đạt `--min-accuracy` và **không có regression** so với `--baseline`; ngược lại trả về **exit code `1`**.
- Trong GitHub Actions (hoặc GitLab CI), chạy bước eval trên mỗi Pull Request:
  ```yaml
  - name: Run Eval Quality Gate
    run: |
      python eval/run_eval.py --url http://localhost:8002 \
        --min-accuracy 1.0 --baseline reports/eval_v2.json \
        --out reports/eval_pr.json
  ```
- Khi kết hợp Branch Protection Rule (bắt buộc check `Run Eval Quality Gate` pass), bất kỳ PR nào làm tụt accuracy hoặc gây regression ở câu từng đúng sẽ trả exit code `1` → CI fail và **tự động chặn merge vào `main`**.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png) *(thấy rõ `AgentHighErrorRate` và `AgentInstanceDown` đang **FIRING**, cùng `AgentHighLatencyP95` và `LLMCostBurnRateHigh` đang **PENDING**)*

**Trả lời Exercise 7.4 (Observability stack):**
- **Tại sao Nginx chặn `/metrics` từ bên ngoài?** Prometheus scrape `/metrics` của các container `agent` trực tiếp trong mạng nội bộ `obs_net`; Nginx chặn truy cập `/metrics` từ internet công cộng để tránh lộ số liệu vận hành nhạy cảm (lưu lượng traffic, chi phí LLM, phiên bản app, số lượng instance).
- **4 Golden Signals trên Grafana (`Day 14 — AI Agent Overview`):** Hiển thị đầy đủ **Traffic** (Requests/s theo status code `200`/`503`, đạt đỉnh ~60 req/s khi chạy Locust), **Latency** (`p50`/`p95`/`p99` dùng `histogram_quantile`), **Errors** (Error rate %), **Saturation** (`agent_in_flight_requests`), kèm **Instances up** và **LLM cost (1h)**.
- **Khoảng cách `avg ↔ p95` & `input token > output token`:**
  - Trên Grafana, `p95` tách xa khỏi `avg`/`p50` (đạt tới `1.95s` khi có tail latency) do một nhóm nhỏ request chậm (`MOCK_SLOW_RATE`) kéo mạnh phân vị cao trong khi `avg` bị phần lớn request nhanh làm phẳng.
  - Số **input tokens luôn lớn hơn output tokens** vì mỗi prompt gửi lên LLM bao gồm cả `SYSTEM_PROMPT` + đoạn context truy xuất từ Knowledge Base (RAG) + câu hỏi của người dùng, dài hơn câu trả lời ngắn gọn mà agent sinh ra.

### 4.2 Thí nghiệm "phá hệ thống"

Chạy trên stack `docker compose -p k5-day14-observability` (tiêm đồng thời lỗi A, B, C và `docker pause` 1 instance D dưới tải Locust 30 users, theo dõi trạng thái qua `http://localhost:9090/api/v1/alerts` mỗi 10s):

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`> 5%`, `for: 1m`) | ~78 giây *(pending từ +18s, firing tại +78s)* | **Error rate** & **Requests/s theo status code** (đường `503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`> 1s`, `for: 2m`) | Pending sau +18s; đủ `for: 2m` (~138s) sẽ chuyển firing | **Latency p95** (chuyển nền đỏ ~1.95s) & biểu đồ **Latency /ask — p50/p95/p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`> $2/giờ`, `for: 2m`) | Firing ở +8s qua API *(tại đỉnh tải cửa sổ 5m trước đó; về sau khi chụp ảnh cuối đang `PENDING` khi tải khởi động lại; chạy từ mốc 0 mất ~2m)* | **LLM cost (1h)** (vọt lên `$1.6389`) & biểu đồ tốc độ tiêu thụ chi phí |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`up == 0`, `for: 30s`) | ~48 giây *(pending từ +8s, firing tại +48s)* | **Instances up** (giảm từ `2` xuống `1`) |
| E | `AGENT_VERSION=v1` | *(Không có alert nào firing)* | N/A | Không có panel hạ tầng nào báo đỏ (latency thậm chí giảm nhẹ ~20ms vì bỏ retrieval) |

*(Ghi chú Thí nghiệm D: dùng `docker pause` thay vì `docker stop` vì `pause` giữ container trong DNS nội bộ nhưng treo process nên Prometheus scrape timeout và ghi `up == 0`; đồng thời nếu Nginx trả `504 Gateway Timeout` khi gọi vào instance bị treo thì lỗi `504` đó sinh ra ở tầng Nginx nên **không hiện trên counter của agent** — production cần giám sát thêm cả tầng Proxy/Ingress.)*

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
- Các alert hạ tầng (4 Golden Signals) chỉ phát hiện sự cố về **tốc độ, lỗi HTTP, availability và chi phí**, không đo được **chất lượng câu trả lời** (v1 vẫn trả HTTP `200 OK` nhanh và rẻ nhưng chỉ đúng `4.35%`).
- Để phát hiện sự cố kiểu E trong production cần kết hợp 3 lớp:
  1. **CI/CD Eval Quality Gate (trước khi deploy):** chạy `eval/run_eval.py --min-accuracy ... --baseline ...` chặn merge/release nếu accuracy tụt hoặc có regression.
  2. **Online Evaluation / Canary Sampling (khi đang chạy thật):** lấy mẫu định kỳ 1–5% traffic thật chấm tự động bằng **LLM-as-a-Judge** (hoặc kiểm tra tỉ lệ retrieval hit / empty context) và đẩy kết quả thành custom Prometheus metric (vd `agent_eval_accuracy_ratio`) để đặt alert.
  3. **User Feedback & Business Metrics:** theo dõi tỉ lệ thumbs-down, tỉ lệ user hỏi lại cùng 1 câu (re-ask rate), hoặc tag `agent_version` trong metric/log để đối chiếu ngay khi release.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger ([screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `5da623d4bdc8fb8122a66724cb0ad36a`
- Tổng thời gian (`POST /ask`): **`1715.47 ms`**
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1697.41 ms`**, chiếm **`98.95%`** tổng thời gian; trong khi `agent.retrieve_context` chỉ mất `15.59 ms` ~ `0.91%`)
- Dòng log tương ứng (grep từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-25T10:01:12.447497+00:00", "level": "INFO", "service": "observable-agent", "instance": "8ac19d66dd40", "event": "llm_call", "trace_id": "5da623d4bdc8fb8122a66724cb0ad36a", "span_id": "692f98c57e21c92b", "request_id": "5f7a0885f607", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.5}
```

*(Trace lỗi trong [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png): `trace_id = 96c96cdb6f0a6c013a661e27ef31bd06`, HTTP `503`, span `chat mock-llm-small` ghi rõ event `exception` với `exception.type = utils.mock_llm.LLMError` và `exception.message = Upstream LLM error: 503 Service Unavailable (mock)`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy chính xác từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (hàng `Aggregated`; trong ngoặc là riêng `POST /ask`):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.81 *(POST /ask: 60.00)* | 190 *(190)* | 230 *(230)* | 1700 *(1700)* | 58 / 7839 = 0.74% *(58 / 7147 = 0.81%)* |
| 3 | 66.10 *(POST /ask: 60.10)* | 190 *(190)* | 220 *(220)* | 1700 *(1700)* | 50 / 7871 = 0.64% *(50 / 7157 = 0.70%)* |

**Giải thích kết quả:**
- **Scale từ 1 lên 3 instance chỉ cải thiện rất nhẹ `p95` (`230ms → 220ms`) và gần như giữ nguyên `RPS` (`65.81 → 66.10`) và `p99` (`1700ms`).**
- **Nút thắt nằm ở đâu?** Không nằm ở CPU của FastAPI/Uvicorn, mà nằm ở **2 điểm**:
  1. **I/O chờ upstream LLM (`chat mock-llm-small`):** chiếm `~99%` thời gian xử lý mỗi request (`~120–180ms` + `1500ms` tail latency ở 3% request). Vì FastAPI xử lý bất đồng bộ (`async/await`), 1 instance vẫn gánh tốt ~66 RPS mà chưa bão hòa CPU, nên thêm 2 instance không thể rút ngắn thời gian chờ LLM provider trả về.
  2. **Giới hạn tốc độ sinh tải của Locust (`wait_time`):** với 100 virtual users có thời gian nghỉ giữa các request, tổng lưu lượng tạo ra chỉ dừng quanh ~66 RPS (dưới ngưỡng bão hòa của cả 1 instance).
- Tuy vậy, scale lên 3 instance vẫn mang lại giá trị lớn về **High Availability (chịu lỗi)** khi 1 container bị pause/crash (như đã chứng minh ở Thí nghiệm D) và tạo dư địa xử lý khi lưu lượng tăng đột biến vượt ngưỡng bão hòa.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Không bao giờ tin chỉ số trung bình (`average`) hay `cost / request`:** Luôn đặt SLO theo **`p95`/`p99`** đi cặp với **`error rate`** để bắt tail latency, và so sánh chất lượng/chi phí AI Agent bằng **`cost / câu đúng`** kết hợp **Golden Dataset + CI Quality Gate** để chặn regression.
  2. **3 trụ cột Observability phải nối với nhau qua `trace_id`:** Metrics (Prometheus/Grafana) báo *có sự cố* → Traces (Jaeger) chỉ ra *span nào chậm/lỗi* (`chat mock-llm-small` chiếm `98.95%`) → Structured JSON Logs (grep theo `trace_id`) cung cấp *ngữ cảnh chi tiết* (`tokens`, `cost`, `error`).
  3. **Scale ngang không tự giải quyết nút thắt I/O upstream:** Trước khi tốn tiền nhân bản server, phải dùng trace & load test tìm đúng bottleneck (CPU queueing vs upstream LLM latency) và nhớ rằng alert hạ tầng không phát hiện được suy giảm chất lượng model (Thí nghiệm E).
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - **Metrics:** `llm_time_to_first_token_seconds` (TTFT cho streaming), `rag_retrieval_empty_total` (tỉ lệ RAG không tìm thấy tài liệu), `agent_eval_online_score` (chấm mẫu tự động bằng LLM-as-a-Judge), `redis_command_duration_seconds` và `rate_limit_rejected_total` (`429`) / `budget_rejected_total` (`402`).
  - **Alerts:** `LLMBudgetNearLimit` (cảnh báo sớm khi chi tiêu đạt 80% ngân sách ngày/tháng), `RAGEmptyContextRateHigh` (phát hiện sớm suy giảm chất lượng retrieval kiểu Thí nghiệm E), và `RedisDown` (cảnh báo ngay khi `/ready` trả `503` kéo dài).

