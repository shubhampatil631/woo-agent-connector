"""Comprehensive tests for async WooClient, rate limiter, retries, pagination, and exceptions."""

import httpx
import pytest
import respx

from woo_connector.client import (
    AuthError,
    NotFoundError,
    RateLimitedError,
    TokenBucket,
    ValidationError,
    WooClient,
    parse_retry_after,
    sanitize_url_for_logging,
)
from woo_connector.config import Settings


@pytest.fixture
def test_config():
    return Settings(
        base_url="https://test-store.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        max_page_size=50,
        rate_limit_rps=100.0,
        request_timeout=5.0,
        max_retries=2,
    )


@respx.mock
async def test_client_429_retry_after_then_success(test_config):
    sleep_calls = []

    async def fake_sleep(duration: float):
        sleep_calls.append(duration)

    route = respx.get("https://test-store.example.com/wp-json/wc/v3/orders")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "Too Many Requests"}),
        httpx.Response(200, json=[{"id": 101, "status": "processing"}]),
    ]

    async with WooClient(config=test_config, sleep_fn=fake_sleep) as client:
        data = await client.get("/wp-json/wc/v3/orders")
        assert len(data) == 1
        assert data[0]["id"] == 101
        assert route.call_count == 2
        assert len(sleep_calls) >= 1
        assert sleep_calls[0] == 2.0


@respx.mock
async def test_client_503_backoff_then_success(test_config):
    sleep_calls = []

    async def fake_sleep(duration: float):
        sleep_calls.append(duration)

    route = respx.get("https://test-store.example.com/wp-json/wc/v3/products")
    route.side_effect = [
        httpx.Response(503, text="Service Temporarily Unavailable"),
        httpx.Response(503, text="Service Temporarily Unavailable"),
        httpx.Response(200, json=[{"id": 50, "name": "Item"}]),
    ]

    async with WooClient(config=test_config, sleep_fn=fake_sleep) as client:
        data = await client.get("/wp-json/wc/v3/products")
        assert len(data) == 1
        assert data[0]["id"] == 50
        assert route.call_count == 3
        assert len(sleep_calls) == 2


@respx.mock
async def test_client_retries_exhausted_rate_limited(test_config):
    async def fast_sleep(duration: float):
        pass

    respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=429,
        headers={"Retry-After": "15"},
        json={"code": "rate_limit_exceeded"},
    )

    async with WooClient(config=test_config, sleep_fn=fast_sleep) as client:
        with pytest.raises(RateLimitedError) as exc_info:
            await client.get("/wp-json/wc/v3/orders")

        err = exc_info.value
        assert err.retry_after == 15.0
        assert "WooCommerce API rate limit reached" in err.agent_message
        assert "15 seconds" in err.agent_message


@respx.mock
async def test_client_401_auth_error_no_retry(test_config):
    route = respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=401,
        json={"code": "woocommerce_rest_cannot_view"},
    )

    async with WooClient(config=test_config) as client:
        with pytest.raises(AuthError) as exc_info:
            await client.get("/wp-json/wc/v3/orders")

        assert exc_info.value.status_code == 401
        assert "Authentication with WooCommerce failed" in exc_info.value.agent_message
        assert route.call_count == 1


@respx.mock
async def test_client_404_not_found(test_config):
    route = respx.get("https://test-store.example.com/wp-json/wc/v3/orders/999").respond(
        status_code=404,
        json={"code": "woocommerce_rest_order_invalid_id"},
    )

    async with WooClient(config=test_config) as client:
        with pytest.raises(NotFoundError) as exc_info:
            await client.get("/wp-json/wc/v3/orders/999")

        assert "resource was not found" in exc_info.value.agent_message
        assert route.call_count == 1


@respx.mock
async def test_client_400_validation_error(test_config):
    respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=400,
        json={"message": "Invalid page parameter"},
    )

    async with WooClient(config=test_config) as client:
        with pytest.raises(ValidationError) as exc_info:
            await client.get("/wp-json/wc/v3/orders", params={"page": -1})

        assert "Invalid request parameters" in exc_info.value.agent_message


@respx.mock
async def test_client_pagination_headers_parsed(test_config):
    respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        headers={"X-WP-Total": "120", "X-WP-TotalPages": "6"},
        json=[{"id": 1}, {"id": 2}],
    )

    async with WooClient(config=test_config) as client:
        page = await client.get_page("/wp-json/wc/v3/orders", page=1, per_page=20)
        assert page.page == 1
        assert page.per_page == 20
        assert page.total == 120
        assert page.total_pages == 6
        assert page.has_more is True
        assert len(page.items) == 2


@respx.mock
async def test_client_pagination_last_page(test_config):
    respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        headers={"X-WP-Total": "120", "X-WP-TotalPages": "6"},
        json=[{"id": 120}],
    )

    async with WooClient(config=test_config) as client:
        page = await client.get_page("/wp-json/wc/v3/orders", page=6, per_page=20)
        assert page.has_more is False


@respx.mock
async def test_client_per_page_clamped_to_max_page_size(test_config):
    route = respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        headers={"X-WP-Total": "50", "X-WP-TotalPages": "1"},
        json=[],
    )

    async with WooClient(config=test_config) as client:
        # Request 150 items, but max_page_size is 50
        page = await client.get_page("/wp-json/wc/v3/orders", per_page=150)
        assert page.per_page == 50

        # Verify respx received clamped query param
        assert route.calls.last.request.url.params["per_page"] == "50"


async def test_token_bucket_rate_limiter_spacing():
    # Simulate a token bucket with rate = 10 tokens/sec
    current_time = 100.0
    sleep_durations = []

    def fake_time():
        return current_time

    async def fake_sleep(seconds: float):
        nonlocal current_time
        sleep_durations.append(seconds)
        current_time += seconds

    bucket = TokenBucket(rate_rps=10.0, capacity=2.0, time_fn=fake_time, sleep_fn=fake_sleep)

    # 1st and 2nd token should be immediate (capacity 2)
    await bucket.acquire(1.0)
    await bucket.acquire(1.0)
    assert len(sleep_durations) == 0

    # 3rd token must wait 0.1s (1/10)
    await bucket.acquire(1.0)
    assert len(sleep_durations) == 1
    assert pytest.approx(sleep_durations[0], rel=1e-2) == 0.1


def test_parse_retry_after_helpers():
    assert parse_retry_after("10") == 10.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid-text") is None


def test_sanitize_url_for_logging():
    raw_url = (
        "http://localhost:8080/wp-json/wc/v3/orders?"
        "consumer_key=ck_secret&consumer_secret=cs_secret&page=1"
    )
    clean_url = sanitize_url_for_logging(raw_url)
    assert "ck_secret" not in clean_url
    assert "cs_secret" not in clean_url
    assert "REDACTED" in clean_url
    assert "page=1" in clean_url


@pytest.mark.asyncio
async def test_client_strictly_rejects_non_get_methods(test_config):
    """Confirm no write HTTP methods (POST, PUT, DELETE, PATCH) can be issued."""
    async with WooClient(config=test_config) as client:
        for write_method in ["POST", "PUT", "DELETE", "PATCH", "post", "delete"]:
            with pytest.raises(ValidationError) as exc:
                await client.request(write_method, "/wp-json/wc/v3/orders")
            assert "prohibited" in str(exc.value).lower()
            assert "strictly read-only" in str(exc.value).lower()


@respx.mock
async def test_client_logging_never_leaks_secrets(test_config, caplog):
    """Confirm client request logs never leak secret keys or sensitive tokens."""
    import logging

    respx.get("https://test-store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        json=[],
    )

    caplog.set_level(logging.DEBUG)
    async with WooClient(config=test_config) as client:
        await client.get(
            "/wp-json/wc/v3/orders",
            params={"consumer_key": "ck_test_key_123", "consumer_secret": "cs_test_sec_456"},
        )

    connector_logs = [
        rec.getMessage() for rec in caplog.records if rec.name == "woo_connector.client"
    ]
    assert len(connector_logs) >= 1
    for msg in connector_logs:
        assert "ck_test_key_123" not in msg
        assert "cs_test_sec_456" not in msg
        assert "REDACTED" in msg
