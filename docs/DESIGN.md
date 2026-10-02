# Architecture & Design Decisions

This document outlines key technical decisions, architectural tradeoffs, and the merchant discovery process for the WooCommerce Agent Studio connector.

---

## 1. Key Architectural Decisions & Tradeoffs

### Decision 1: Read-Only by Design (Zero Write Primitives)
- **Rationale**: An AI agent operating directly on merchant store data introduces significant operational risks if allowed to mutate state autonomously. Accidental order cancellations, unauthorized refunds, or inventory miscounts could damage merchant trust and cause real financial losses.
- **Tradeoff**: The agent cannot directly execute fulfillment or refunds; it acts strictly as an intelligence and triage assistant. Actions requiring state mutation are routed to human operators.
- **Enforcement**: No write/update/delete endpoints are registered in `tools.py` or exposed via FastMCP. `STRICT_READONLY=true` can be enabled to reject startup if the supplied API key has write permissions in WooCommerce.

### Decision 2: Client-Side Token Bucket Limiter + Full Jitter Retries
- **Rationale**: WooCommerce stores frequently run on shared hosting, managed WordPress (e.g., WP Engine, Kinsta), or behind WAFs with strict burst rate limits (often 5–25 req/sec). Without client-side coordination, concurrent LLM tool calls can easily trigger HTTP 429 Too Many Requests.
- **Implementation**: A concurrency-safe `TokenBucket` rate limiter (`RATE_LIMIT_RPS=5.0`) regulates outbound requests. If 429 or 5xx errors occur, the client applies exponential backoff with full jitter, honoring `Retry-After` headers.
- **Tradeoff**: Introduces minor synthetic latency during heavy traffic bursts in exchange for zero dropped requests.

### Decision 3: Connector-Side PII Redaction Engine
- **Rationale**: Defense-in-depth requires that customer PII (emails, phone numbers, physical street addresses) is stripped *before* entering LLM prompts or vendor context windows.
- **Implementation**: `redact.py` transforms names to initials (`Jane D.`), emails to masked strings (`j***@example.com`), phone numbers to masked tails (`***-***-**67`), and addresses to city/state/country only.
- **Tradeoff**: The agent cannot read verbatim customer street addresses for door-to-door delivery debugging, but it prevents accidental PII leakage into training loops or conversational transcripts.

### Decision 4: Standardized FastMCP over Custom API Gateways
- **Rationale**: Adopting the official Model Context Protocol (MCP) standard allows seamless interoperability with Razorpay Agent Studio, Claude Desktop, Cursor, and any MCP-compliant runtime.
- **Implementation**: Leverages `FastMCP` from the official `mcp` SDK to register typed schemas, error codes, and dynamic resources (`woo://store/status`, `woo://docs/capabilities`).
- **Tradeoff**: Requires pinning to compatible SDK versions (`mcp>=1.2.0,<2.0.0`), but eliminates custom agent client libraries.

### Decision 5: Dual Authentication Strategies
- **Rationale**: Merchants need simple setup in development and secure standards in production.
- **Implementation**:
  1. `APIKeyAuth`: HTTP Basic Auth over HTTPS (RFC 7617), with query parameter fallback and explicit warnings for plain HTTP dev sandbox testing.
  2. `OAuthAppAuth`: WooCommerce `/wc-auth/v1/authorize` app approval flow for non-technical merchant onboarding.

---

## 2. Forward-Deployed Engineer: Merchant Discovery Field Guide

Before deploying this connector to a live merchant in Razorpay Agent Studio, a Forward-Deployed Engineer (FDE) must conduct a discovery session covering five critical areas:

### 1. Workflow & User Persona
- *What specific workflow is the agent automating?* (e.g., Customer Support WISMO "Where is my order", Tier-1 Returns Triage, or Internal Ops Stock Monitoring).
- *Who interacts with the agent?* (External shoppers via chat widget vs. internal customer support agents on Zendesk/Freshdesk).

### 2. Data Visibility & Privacy Compliance
- *What customer data is permitted in the agent's context window?*
- *Are there regional compliance mandates (e.g., GDPR, DPDP India) requiring strict redaction or audit logging of customer order queries?*

### 3. Traffic Volume & Hosting Infrastructure
- *What is the merchant's peak order volume and query traffic (queries/sec)?*
- *Where is WooCommerce hosted (self-hosted VPS, AWS, WP Engine, Kinsta)?* What upstream rate limits or Cloudflare WAF rules are active?

### 4. Custom Data & Plugin Dependencies
- *Does the merchant use custom order statuses* (e.g., `awaiting-fulfillment`, `packed`, `dispatched` from shipping plugins like Shiprocket/Delhivery)?
- *Are there custom order meta fields (tracking URLs, delivery dates) that should be exposed in `OrderDetail`?*

### 5. Success Metrics & Rollback Strategy
- *What is the quantitative definition of success?* (e.g., 50% reduction in support ticket response time, 40% deflection of WISMO tickets).
- *What is the fallback process if the store's REST API goes down?*
