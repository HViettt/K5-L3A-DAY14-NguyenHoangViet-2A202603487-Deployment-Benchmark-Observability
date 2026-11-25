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

*(Đang chờ thực hiện ở CP8)*

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

*(Đang chờ thực hiện ở CP8)*

### 4.3 Debug bằng trace

*(Đang chờ thực hiện ở CP8)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** *(Đang chờ thực hiện ở CP8)*

---

## 6. Kết luận

*(Đang chờ hoàn thiện ở CP8)*
