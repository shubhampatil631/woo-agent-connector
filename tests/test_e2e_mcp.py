"""End-to-end tests for FastMCP server against mock WooCommerce.

Tests all registered tools through the FastMCP execution interface, covering:
- Happy paths for all 9 read primitives
- Not-found entity handling
- Invalid input validation
- Authentication failures
- Multi-page pagination (3 pages)
- PII redaction on vs off
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from tests.mock_woo import app as mock_app
from tests.mock_woo import state as mock_state
from woo_connector.client import WooClient
from woo_connector.config import Settings
from woo_connector.server import mcp


@pytest.fixture(autouse=True)
def reset_mock_state():
    """Reset mock state before each test."""
    mock_state.reset_data()
    mock_state.rate_limit_429_count = 0
    mock_state.fail_503_count = 0
    mock_state.require_auth = True
    mock_state.expected_key = "ck_test_mock_key"
    mock_state.expected_secret = "cs_test_mock_secret"


def get_mock_client(
    pii_mode: str = "redacted",
    consumer_key: str = "ck_test_mock_key",
    consumer_secret: str = "cs_test_mock_secret",
) -> WooClient:
    """Create a WooClient routed directly to the mock FastAPI app via ASGITransport."""
    config = Settings(
        base_url="https://mock-woo.local",
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        pii_mode=pii_mode,
        rate_limit_rps=50.0,
        request_timeout=5.0,
        max_retries=3,
    )
    from woo_connector.auth import get_auth_strategy
    auth_strategy = get_auth_strategy(config)
    transport = ASGITransport(app=mock_app)
    raw_http_client = AsyncClient(
        transport=transport,
        base_url="https://mock-woo.local",
        auth=auth_strategy,
    )
    return WooClient(config=config, auth=auth_strategy, http_client=raw_http_client)


async def call_mcp(tool_name: str, arguments: dict[str, Any], client: WooClient) -> Any:
    """Helper to invoke an MCP tool with a custom client."""
    from unittest.mock import patch

    with patch("woo_connector.server.get_client", return_value=client):
        result = await mcp.call_tool(tool_name, arguments)
        if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[1], dict):
            return result[1]
        if isinstance(result, list) and len(result) > 0 and hasattr(result[0], "text"):
            try:
                return json.loads(result[0].text)
            except Exception:
                return result[0].text
        return result


@pytest.mark.asyncio
async def test_e2e_mcp_all_tools_happy_path():
    """Verify all 9 read tools succeed through the FastMCP tool interface."""
    client = get_mock_client()

    # 1. list_orders
    res_orders = await call_mcp("list_orders", {"page": 1, "per_page": 5}, client)
    assert "items" in res_orders
    assert len(res_orders["items"]) == 5
    assert res_orders["total"] == 25
    assert res_orders["has_more"] is True

    # 2. get_order
    res_order = await call_mcp("get_order", {"order_id": 1001}, client)
    assert res_order["id"] == 1001
    assert res_order["status"] in [
        "processing", "completed", "on-hold", "pending", "failed", "refunded"
    ]
    assert "line_items" in res_order
    assert len(res_order["line_items"]) >= 1

    # 3. search_orders
    res_search_orders = await call_mcp("search_orders", {"query": "customer1@example.com"}, client)
    assert "items" in res_search_orders
    assert len(res_search_orders["items"]) >= 1

    # 4. list_products
    res_products = await call_mcp("list_products", {"page": 1, "per_page": 2}, client)
    assert "items" in res_products
    assert len(res_products["items"]) == 2
    assert res_products["total"] == 4

    # 5. get_product
    res_product = await call_mcp("get_product", {"product_id": 101}, client)
    assert res_product["id"] == 101
    assert res_product["sku"] == "SLEEVE-LTH-01"

    # 6. search_products
    res_search_prod = await call_mcp("search_products", {"query": "Keyboard"}, client)
    assert "items" in res_search_prod
    assert any(p["id"] == 102 for p in res_search_prod["items"])

    # 7. get_stock by product_id and sku
    res_stock_id = await call_mcp("get_stock", {"product_id_or_sku": "101"}, client)
    assert res_stock_id["product_id"] == 101
    assert res_stock_id["stock_quantity"] == 4
    assert res_stock_id["low_stock"] is True

    res_stock_sku = await call_mcp("get_stock", {"product_id_or_sku": "KB-MECH-RGB"}, client)
    assert res_stock_sku["product_id"] == 102
    assert res_stock_sku["stock_quantity"] == 25
    assert res_stock_sku["low_stock"] is False

    # 8. list_low_stock
    res_low = await call_mcp("list_low_stock", {"threshold": 5}, client)
    assert "items" in res_low
    assert any(p["sku"] == "SLEEVE-LTH-01" for p in res_low["items"])

    # 9. get_store_status
    res_status = await call_mcp("get_store_status", {}, client)
    assert res_status["connected"] is True
    assert res_status["currency"] == "INR"


@pytest.mark.asyncio
async def test_e2e_mcp_not_found_handling():
    """Verify clean, agent-actionable errors on missing resources."""
    client = get_mock_client()

    # Missing order
    res_order = await call_mcp("get_order", {"order_id": 999999}, client)
    assert res_order["code"] == "NOT_FOUND"
    assert "not found" in res_order["message"].lower()

    # Missing product
    res_prod = await call_mcp("get_product", {"product_id": 999999}, client)
    assert res_prod["code"] == "NOT_FOUND"
    assert "not found" in res_prod["message"].lower()

    # Missing SKU stock
    res_stock = await call_mcp("get_stock", {"product_id_or_sku": "NONEXISTENT-SKU"}, client)
    assert res_stock["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_e2e_mcp_invalid_inputs():
    """Verify client-side validation errors for invalid parameters."""
    client = get_mock_client()

    # Invalid order status
    res = await call_mcp("list_orders", {"status": "invalid_status_xyz"}, client)
    assert res["code"] == "INVALID_INPUT"
    assert "invalid_status_xyz" in res["message"]

    # Empty search query
    res_search = await call_mcp("search_orders", {"query": "  "}, client)
    assert res_search["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_e2e_mcp_auth_failure():
    """Verify unauthorized response mapped to actionable AuthError."""
    bad_client = get_mock_client(consumer_key="ck_invalid", consumer_secret="cs_invalid")

    res = await call_mcp("list_orders", {}, bad_client)
    assert res["code"] == "AUTH_FAILED"
    assert "credentials are invalid" in res["message"].lower()


@pytest.mark.asyncio
async def test_e2e_mcp_pagination_across_3_pages():
    """Verify pagination traversal across 3 distinct pages."""
    client = get_mock_client()

    p1 = await call_mcp("list_orders", {"page": 1, "per_page": 10}, client)
    assert p1["page"] == 1
    assert len(p1["items"]) == 10
    assert p1["total"] == 25
    assert p1["total_pages"] == 3
    assert p1["has_more"] is True

    p2 = await call_mcp("list_orders", {"page": 2, "per_page": 10}, client)
    assert p2["page"] == 2
    assert len(p2["items"]) == 10
    assert p2["has_more"] is True

    p3 = await call_mcp("list_orders", {"page": 3, "per_page": 10}, client)
    assert p3["page"] == 3
    assert len(p3["items"]) == 5
    assert p3["has_more"] is False

    # Verify all 25 items are distinct IDs
    ids = [item["id"] for item in p1["items"] + p2["items"] + p3["items"]]
    assert len(ids) == 25
    assert len(set(ids)) == 25


@pytest.mark.asyncio
async def test_e2e_mcp_redaction_toggle():
    """Verify PII masking behavior toggled between redacted and full."""
    # 1. Redacted mode (default)
    client_redacted = get_mock_client(pii_mode="redacted")
    res_red = await call_mcp("get_order", {"order_id": 1001}, client_redacted)

    assert "customer1@example.com" not in res_red["billing"]["email"]
    assert res_red["billing"]["email"] == "c***@example.com"
    assert res_red["billing"]["phone"].endswith("01")
    assert "9876" not in res_red["billing"]["phone"]
    assert res_red["billing"]["first_name"] == "Jane"
    assert res_red["billing"]["last_name"] == "D."

    # 2. Full mode (unmasked)
    client_full = get_mock_client(pii_mode="full")
    res_full = await call_mcp("get_order", {"order_id": 1001}, client_full)

    assert res_full["billing"]["email"] == "customer1@example.com"
    assert res_full["billing"]["phone"] == "+919876543201"
    assert res_full["billing"]["first_name"] == "Jane"
    assert res_full["billing"]["last_name"] == "Doe"
