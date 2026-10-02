# System Limitations & Future Engineering Roadmap

An honest overview of current system boundaries, technical tradeoffs in v0.1.0, and the prioritized roadmap for enterprise production scale.

---

## 1. Current System Limitations

1. **Request-Response Polling Architecture**:
   - The connector relies on outbound HTTP GET polling. It does not ingest incoming WooCommerce webhooks (`order.created`, `order.updated`), meaning state changes are discovered only upon active agent query.

2. **Single-Store Process Binding**:
   - A running connector instance binds to one set of merchant credentials (`WOO_BASE_URL`, `WOO_CONSUMER_KEY`). Multi-tenant environments require spawning separate processes or containers per merchant.

3. **WooCommerce Search Query Semantics**:
   - `search_orders` and `search_products` rely on native WooCommerce SQL `LIKE` queries against `wp_posts` and `wp_postmeta`. Stores with millions of historical orders without specialized Elasticsearch/MySQL indexing may experience higher query latencies.

4. **In-Memory Rate Limiting**:
   - The `TokenBucket` limiter operates in-memory per process. In horizontally scaled deployments with multiple connector replicas, rate limits are not shared across instances without an external Redis coordinator.

5. **Environment-Based Secret Management**:
   - Credentials currently load from environment variables or `.env` files rather than dynamic retrieval from an enterprise secret manager (e.g., AWS Secrets Manager or HashiCorp Vault).

---

## 2. What I'd Build Next (Enterprise Roadmap)

### 1. Webhook Ingestion & Edge Cache Invalidation
- Build an inbound webhook receiver for `order.created`, `order.updated`, and `product.restocked` events.
- Cache hot order summaries and inventory counts in Redis/Upstash for sub-10ms tool execution and near-zero load on the merchant's WordPress server.

### 2. True OAuth2 via Razorpay Merchant Credential Vault
- Integrate with Razorpay's centralized KMS/Vault service to dynamically decrypt store credentials with short-lived session tokens, eliminating persistent consumer secrets.

### 3. Multi-Tenant Request Multiplexing
- Refactor the HTTP/SSE transport layer to accept a tenant identifier in request headers (e.g., `X-Merchant-ID`) and dynamically look up isolated credentials per invocation.

### 4. Tamper-Evident Audit Logging
- Emit structured JSON audit logs for every tool call (capturing correlation ID, timestamp, caller ID, tool name, sanitized query parameters, and latency) to meet enterprise security and compliance standards.

### 5. Human-in-the-Loop (HITL) Action Primitives
- Introduce safe write capabilities (e.g., `create_order_note`, `tag_order_for_review`, `initiate_refund_proposal`) governed by a two-phase commit: the agent proposes an action, and the merchant approves via a secure one-time token.

### 6. Contract Testing Across WooCommerce Versions
- Add CI/CD contract tests against a matrix of pinned WooCommerce major versions (v7.x, v8.x, v9.x) and PHP runtimes (8.1, 8.2, 8.3) to prevent regression on upstream API schema drifts.

### 7. Production Observability (OpenTelemetry & Prometheus)
- Export standard OpenTelemetry spans and Prometheus metrics:
  - `woo_connector_requests_total{tool="list_orders", status="200"}`
  - `woo_connector_latency_seconds_bucket{tool="get_stock"}`
  - `woo_connector_rate_limit_retries_total`
