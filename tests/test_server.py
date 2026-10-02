"""Tests for FastMCP server, tool registration, resources, and auth middleware."""

import pytest
import respx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from woo_connector.config import Settings
from woo_connector.server import (
    BearerAuthMiddleware,
    capabilities_resource,
    mcp,
    run_startup_check,
    store_status_resource,
)


@pytest.fixture
def mock_settings():
    return Settings(
        base_url="https://store.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        connector_api_key="secret-bearer-token-12345",
        strict_readonly=True,
    )


async def test_all_tools_registered_on_mcp():
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "list_orders",
        "get_order",
        "search_orders",
        "list_products",
        "get_product",
        "search_products",
        "get_stock",
        "list_low_stock",
        "get_store_status",
    }
    assert expected_tools.issubset(tool_names)


async def test_capabilities_resource():
    content = await capabilities_resource()
    assert "WooCommerce Agent Studio Connector Capabilities" in content
    assert "What the Agent CAN Do" in content
    assert "What the Agent CANNOT Do" in content


@respx.mock
async def test_store_status_resource():
    respx.get("http://localhost:8080/wp-json/wc/v3/system_status").respond(
        status_code=200,
        json={
            "environment": {"wp_version": "6.4.3", "version": "8.5.1"},
            "settings": {"currency": "USD", "currency_symbol": "$"},
        },
    )
    content = await store_status_resource()
    assert "connected" in content
    assert "6.4.3" in content


@respx.mock
async def test_startup_check_success(mock_settings):
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=200,
        json={"environment": {"wp_version": "6.4"}},
    )
    # Should complete without error
    await run_startup_check(mock_settings)


@respx.mock
async def test_startup_check_failure(mock_settings):
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=401,
        json={"code": "unauthorized"},
    )
    with pytest.raises(SystemExit) as exc:
        await run_startup_check(mock_settings)
    assert exc.value.code == 1


def test_bearer_auth_middleware_flow():
    async def dummy_endpoint(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/test", dummy_endpoint)])
    app.add_middleware(BearerAuthMiddleware, api_key="expected-secure-token")

    client = TestClient(app)

    # 1. Missing Authorization header -> 401
    resp_no_header = client.get("/test")
    assert resp_no_header.status_code == 401
    assert "Missing Bearer token" in resp_no_header.json()["error"]

    # 2. Invalid Token -> 401
    resp_invalid = client.get("/test", headers={"Authorization": "Bearer wrong-token"})
    assert resp_invalid.status_code == 401
    assert "Invalid connector API key" in resp_invalid.json()["error"]

    # 3. Valid Token -> 200
    resp_valid = client.get("/test", headers={"Authorization": "Bearer expected-secure-token"})
    assert resp_valid.status_code == 200
    assert resp_valid.json() == {"status": "ok"}
