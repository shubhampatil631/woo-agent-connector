# Merchant Business Impact & Measurement Plan

*(Note: This document defines the measurement plan and instrumentation strategy for evaluating merchant impact prior to live deployment. Results will be gathered during merchant pilot phases).*

---

## 1. Baseline vs. Target Key Performance Indicators (KPIs)

| Metric | Current Manual Baseline | Target with Agent Studio Connector | Measurement Method |
| :--- | :--- | :--- | :--- |
| **Order Status Lookup (WISMO)** | 90–180 seconds (human opens WP Admin, searches order ID, reads customer notes) | **< 2.5 seconds** (instant tool invocation & response generation) | End-to-end tool execution latency logs |
| **Inventory / Stock Verification** | 60–120 seconds (support checks catalog stock across variations) | **< 1.0 second** (direct SKU lookup via `get_stock`) | Upstream request duration telemetry |
| **Tier-1 Ticket Deflection Rate** | 0% (all customer status inquiries reach human support queue) | **40% – 60%** automated resolution for order/inventory questions | Support ticketing system tagging (Zendesk / Freshdesk) |
| **Connector Reliability / Error Rate** | N/A | **< 0.1%** unhandled failures (excluding store downtime) | Ratio of `5xx` / unhandled exceptions to total queries |
| **LLM Context Token Efficiency** | Raw Woo payload (~2,500 tokens per order) | **~350 tokens** per `OrderDetail` (>75% token reduction) | Token count benchmarking on normalized responses |

---

## 2. Measurement & Instrumentation Strategy

To validate these targets in production, the connector is instrumented with four observability layers:

### 1. Request Correlation & Latency Logging
Every upstream request logs structured metadata with a unique `correlation_id`:
```json
{
  "timestamp": "2026-10-02T10:15:30Z",
  "correlation_id": "f6d6b54a",
  "method": "GET",
  "path": "/wp-json/wc/v3/orders",
  "status_code": 200,
  "duration_ms": 142.5,
  "tool": "list_orders"
}
```

### 2. Upstream Resilience & Rate-Limit Tracking
Track retry counts and backoff frequency to assess whether `RATE_LIMIT_RPS` requires merchant-specific tuning:
- Number of HTTP 429 responses intercepted.
- Total wait time introduced by `Retry-After` backoffs.
- Number of exhausted retry exceptions (`RateLimitedError`).

### 3. PII Masking Verification Rate
- Automated CI regression tests verifying 100% masking of raw emails, phone numbers, and street addresses in `PII_MODE=redacted`.

### 4. Pilot Evaluation Methodology
1. **Phase 1 (Shadow Mode)**: Run connector queries in parallel with human support tickets to verify accuracy and response times without sending outputs to customers.
2. **Phase 2 (Assisted Agent Mode)**: Present connector-generated order summaries to human support reps to measure time-to-first-response improvements.
3. **Phase 3 (Autonomous Tier-1 Resolution)**: Enable direct conversational answers for order status and stock queries, tracking resolution and customer satisfaction (CSAT) scores.
