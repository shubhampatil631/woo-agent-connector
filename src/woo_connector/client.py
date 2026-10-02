"""Async client for WooCommerce REST API.
Includes token-bucket rate limiting, retries, and pagination.
"""

import asyncio
import email.utils
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from woo_connector.auth import AuthStrategy, get_auth_strategy
from woo_connector.config import Settings, settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class WooConnectorError(Exception):
    """Base exception for all WooCommerce connector errors."""

    def __init__(self, message: str, agent_message: str | None = None):
        super().__init__(message)
        self._agent_message = agent_message or message

    @property
    def agent_message(self) -> str:
        """Plain-English, actionable message designed for LLM agent relay."""
        return self._agent_message


class AuthError(WooConnectorError):
    """Authentication or authorization failure (HTTP 401 / 403)."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(
            message=message,
            agent_message=(
                "Authentication with WooCommerce failed. "
                "The API credentials are invalid or lack read permissions."
            ),
        )
        self.status_code = status_code


class NotFoundError(WooConnectorError):
    """Requested resource was not found (HTTP 404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            agent_message="The requested WooCommerce resource was not found.",
        )


class RateLimitedError(WooConnectorError):
    """WooCommerce API rate limit exhausted after retries (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None):
        retry_msg = (
            f" Please retry in {int(retry_after)} seconds."
            if retry_after and retry_after > 0
            else " Please wait before retrying."
        )
        super().__init__(
            message=message,
            agent_message=f"WooCommerce API rate limit reached.{retry_msg}",
        )
        self.retry_after = retry_after


class UpstreamError(WooConnectorError):
    """WooCommerce server or gateway error (HTTP 500/502/503/504)."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(
            message=message,
            agent_message=(
                f"WooCommerce store is temporarily unavailable (HTTP {status_code}). "
                "Please retry in a moment."
            ),
        )
        self.status_code = status_code


class ValidationError(WooConnectorError):
    """Invalid input parameter or request payload (HTTP 400)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            agent_message=f"Invalid request parameters for WooCommerce: {message}",
        )


@dataclass(frozen=True)
class Page(Generic[T]):
    """Paginated collection of WooCommerce resources."""

    items: list[T]
    page: int
    per_page: int
    total: int | None = None
    total_pages: int | None = None
    has_more: bool = False


class TokenBucket:
    """Task-safe token bucket rate limiter with pluggable time/sleep for testing."""

    def __init__(
        self,
        rate_rps: float,
        capacity: float | None = None,
        time_fn: Any = None,
        sleep_fn: Any = None,
    ):
        self.rate = max(0.1, rate_rps)
        self.capacity = capacity if capacity is not None else self.rate
        self.tokens = self.capacity
        self.time_fn = time_fn or time.monotonic
        self.sleep_fn = sleep_fn or asyncio.sleep
        self.last_update = self.time_fn()
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens, asynchronously sleeping if bucket is depleted."""
        async with self._get_lock():
            while True:
                now = self.time_fn()
                elapsed = max(0.0, now - self.last_update)
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= (tokens - 1e-7):
                    self.tokens = max(0.0, self.tokens - tokens)
                    return

                needed = tokens - self.tokens
                wait_time = max(0.0, needed / self.rate)
                res = self.sleep_fn(wait_time)
                if asyncio.iscoroutine(res):
                    await res


def parse_retry_after(header_value: str | None) -> float | None:
    """Parse HTTP Retry-After header as either seconds integer or HTTP date."""
    if not header_value:
        return None
    header_clean = header_value.strip()

    # Try numeric seconds
    try:
        seconds = float(header_clean)
        return max(0.0, seconds)
    except ValueError:
        pass

    # Try HTTP date string (RFC 2822 / RFC 7231)
    try:
        target_dt = email.utils.parsedate_to_datetime(header_clean)
        now_dt = datetime.now(UTC)
        diff = (target_dt - now_dt).total_seconds()
        return max(0.0, diff)
    except Exception:
        return None


def sanitize_url_for_logging(url: str | httpx.URL) -> str:
    """Remove sensitive authentication credentials from URL before logging."""
    url_str = str(url)
    parts = urlsplit(url_str)
    if not parts.query:
        return url_str

    params = parse_qsl(parts.query, keep_blank_values=True)
    sanitized = []
    for k, v in params:
        if k in ("consumer_key", "consumer_secret", "password", "token"):
            sanitized.append((k, "***[REDACTED]"))
        else:
            sanitized.append((k, v))

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(sanitized),
        parts.fragment,
    ))


class WooClient:
    """High-performance async client for WooCommerce REST API."""

    RETRY_STATUS_CODES = {429, 502, 503, 504}

    def __init__(
        self,
        config: Settings = settings,
        auth: AuthStrategy | None = None,
        rate_limiter: TokenBucket | None = None,
        http_client: httpx.AsyncClient | None = None,
        sleep_fn: Any = asyncio.sleep,
    ):
        self.config = config
        self.auth = auth or get_auth_strategy(config)
        self.rate_limiter = rate_limiter or TokenBucket(
            rate_rps=config.rate_limit_rps,
            sleep_fn=sleep_fn,
        )
        self.sleep_fn = sleep_fn
        self._external_client = http_client is not None
        self._client = http_client or httpx.AsyncClient(
            base_url=str(config.base_url).rstrip("/"),
            auth=self.auth,
            timeout=config.request_timeout,
        )

    async def __aenter__(self) -> "WooClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self) -> None:
        """Close underlying HTTP client session if self-managed."""
        if not self._external_client and self._client:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute request, strictly prohibiting non-GET HTTP methods."""
        if method.upper() != "GET":
            raise ValidationError(
                f"HTTP method '{method.upper()}' is prohibited. "
                "The WooCommerce Agent Studio Connector is strictly read-only."
            )
        return await self.get(path=path, params=params)

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a read-only GET request with rate limiting and exponential retries."""
        normalized_path = "/" + path.lstrip("/")
        query_params = dict(params) if params else {}

        attempt = 0
        last_exception: Exception | None = None

        while attempt <= self.config.max_retries:
            await self.rate_limiter.acquire()
            corr_id = uuid.uuid4().hex[:8]
            start_time = time.monotonic()

            try:
                response = await self._client.get(normalized_path, params=query_params)
                latency_ms = (time.monotonic() - start_time) * 1000.0

                safe_url = sanitize_url_for_logging(response.request.url)
                logger.debug(
                    "[%s] GET %s -> HTTP %d (%.1fms)",
                    corr_id,
                    safe_url,
                    response.status_code,
                    latency_ms,
                )

                if response.status_code in (200, 201):
                    return response.json()

                if response.status_code == 400:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("message", response.text)
                    except Exception:
                        err_msg = response.text
                    raise ValidationError(err_msg)

                if response.status_code in (401, 403):
                    raise AuthError(
                        f"WooCommerce authentication failed with HTTP {response.status_code}",
                        status_code=response.status_code,
                    )

                if response.status_code == 404:
                    raise NotFoundError(f"Resource at {normalized_path} not found")

                if response.status_code in self.RETRY_STATUS_CODES:
                    attempt += 1
                    if attempt > self.config.max_retries:
                        if response.status_code == 429:
                            retry_after = parse_retry_after(response.headers.get("Retry-After"))
                            raise RateLimitedError(
                                "Rate limit exceeded and max retries exhausted",
                                retry_after=retry_after,
                            )
                        raise UpstreamError(
                            f"WooCommerce service unavailable (HTTP {response.status_code})",
                            status_code=response.status_code,
                        )

                    # Calculate backoff delay
                    if response.status_code == 429 and "Retry-After" in response.headers:
                        delay = parse_retry_after(response.headers["Retry-After"]) or 1.0
                    else:
                        base_backoff = 0.5 * (self.config.backoff_factor ** attempt)
                        delay = random.uniform(0.1, max(0.2, base_backoff))

                    logger.warning(
                        "[%s] HTTP %d encountered. Retrying in %.2fs (attempt %d/%d)...",
                        corr_id,
                        response.status_code,
                        delay,
                        attempt,
                        self.config.max_retries,
                    )
                    await self.sleep_fn(delay)
                    continue

                # Any other unexpected non-retryable 4xx/5xx
                raise UpstreamError(
                    f"WooCommerce API error: HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_exception = exc
                attempt += 1
                if attempt > self.config.max_retries:
                    raise UpstreamError(
                        f"Network failure connecting to WooCommerce: {exc}",
                        status_code=504 if isinstance(exc, httpx.TimeoutException) else 503,
                    ) from exc

                base_backoff = 0.5 * (self.config.backoff_factor ** attempt)
                delay = random.uniform(0.1, max(0.2, base_backoff))
                logger.warning(
                    "[%s] Network error %s. Retrying in %.2fs (attempt %d/%d)...",
                    corr_id,
                    type(exc).__name__,
                    delay,
                    attempt,
                    self.config.max_retries,
                )
                await self.sleep_fn(delay)

        if last_exception:
            raise UpstreamError(f"Request failed after retries: {last_exception}")
        raise UpstreamError("Request failed after retries")

    async def get_page(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int | None = None,
    ) -> Page[Any]:
        """Execute a paginated read-only GET request and parse pagination headers."""
        normalized_path = "/" + path.lstrip("/")
        query_params = dict(params) if params else {}

        # Clamp requested per_page to MAX_PAGE_SIZE
        target_per_page = per_page if per_page is not None else self.config.max_page_size
        clamped_per_page = max(1, min(target_per_page, self.config.max_page_size))

        query_params["page"] = page
        query_params["per_page"] = clamped_per_page

        attempt = 0
        while attempt <= self.config.max_retries:
            await self.rate_limiter.acquire()
            corr_id = uuid.uuid4().hex[:8]
            start_time = time.monotonic()

            try:
                response = await self._client.get(normalized_path, params=query_params)
                latency_ms = (time.monotonic() - start_time) * 1000.0

                safe_url = sanitize_url_for_logging(response.request.url)
                logger.debug(
                    "[%s] GET PAGE %s -> HTTP %d (%.1fms)",
                    corr_id,
                    safe_url,
                    response.status_code,
                    latency_ms,
                )

                if response.status_code in (200, 201):
                    items = response.json()
                    if not isinstance(items, list):
                        items = [items]

                    total_str = response.headers.get("X-WP-Total")
                    total_pages_str = response.headers.get("X-WP-TotalPages")

                    total = int(total_str) if total_str and total_str.isdigit() else None
                    total_pages = (
                        int(total_pages_str)
                        if total_pages_str and total_pages_str.isdigit()
                        else None
                    )

                    if total_pages is not None:
                        has_more = page < total_pages
                    else:
                        has_more = len(items) == clamped_per_page

                    return Page(
                        items=items,
                        page=page,
                        per_page=clamped_per_page,
                        total=total,
                        total_pages=total_pages,
                        has_more=has_more,
                    )

                if response.status_code == 400:
                    try:
                        err_msg = response.json().get("message", response.text)
                    except Exception:
                        err_msg = response.text
                    raise ValidationError(err_msg)

                if response.status_code in (401, 403):
                    raise AuthError(
                        f"Authentication failed (HTTP {response.status_code})",
                        status_code=response.status_code,
                    )

                if response.status_code == 404:
                    raise NotFoundError(f"Resource {normalized_path} not found")

                if response.status_code in self.RETRY_STATUS_CODES:
                    attempt += 1
                    if attempt > self.config.max_retries:
                        if response.status_code == 429:
                            retry_after = parse_retry_after(response.headers.get("Retry-After"))
                            raise RateLimitedError(
                                "Rate limit reached and retries exhausted",
                                retry_after=retry_after,
                            )
                        raise UpstreamError(
                            f"Upstream error (HTTP {response.status_code})",
                            status_code=response.status_code,
                        )

                    if response.status_code == 429 and "Retry-After" in response.headers:
                        delay = parse_retry_after(response.headers["Retry-After"]) or 1.0
                    else:
                        delay = random.uniform(
                            0.1, max(0.2, 0.5 * (self.config.backoff_factor ** attempt))
                        )

                    logger.warning(
                        "[%s] Retrying page query in %.2fs (attempt %d/%d)...",
                        corr_id,
                        delay,
                        attempt,
                        self.config.max_retries,
                    )
                    await self.sleep_fn(delay)
                    continue

                raise UpstreamError(
                    f"WooCommerce API error: HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                attempt += 1
                if attempt > self.config.max_retries:
                    raise UpstreamError(
                        f"Network failure: {exc}",
                        status_code=504 if isinstance(exc, httpx.TimeoutException) else 503,
                    ) from exc

                delay = random.uniform(
                    0.1, max(0.2, 0.5 * (self.config.backoff_factor ** attempt))
                )
                await self.sleep_fn(delay)

        raise UpstreamError("Page request failed after retries")


# Backward compatibility alias
WooCommerceClient = WooClient
