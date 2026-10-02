"""Integration tests for transport-agnostic read primitive tools using respx and fixtures."""

import json
from pathlib import Path

import pytest
import respx

from woo_connector.client import (
    AuthError,
    NotFoundError,
    RateLimitedError,
    UpstreamError,
    ValidationError,
    WooClient,
)
from woo_connector.config import PIIMode, Settings
from woo_connector.models import OrderDetail, OrderSummary, ProductSummary, StockInfo, StoreStatus
from woo_connector.tools import (
    get_order,
    get_product,
    get_stock,
    get_store_status,
    list_low_stock,
    list_orders,
    list_products,
    map_exception_to_tool_error,
    search_orders,
    search_products,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str):
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_client():
    cfg = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        pii_mode=PIIMode.REDACTED,
        rate_limit_rps=100.0,
    )
    return WooClient(config=cfg)


@respx.mock
async def test_list_orders_success(mock_client):
    data = load_fixture("orders_list_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        headers={"X-WP-Total": "2", "X-WP-TotalPages": "1"},
        json=data,
    )

    result = await list_orders(mock_client, status="processing", page=1, per_page=10)
    assert result.total == 2
    assert len(result.items) == 2
    assert isinstance(result.items[0], OrderSummary)
    assert result.items[0].id == 101
    assert result.items[0].customer_ref == "Customer #12"
    assert result.items[1].customer_ref == "a***@example.com"
    assert result.has_more is False


@respx.mock
async def test_list_orders_validation():
    cfg = Settings(base_url="https://store.example.com", consumer_key="ck", consumer_secret="cs")
    client = WooClient(config=cfg)

    with pytest.raises(ValidationError):
        await list_orders(client, status="invalid_status")

    with pytest.raises(ValidationError):
        await list_orders(client, after="not-a-date")

    with pytest.raises(ValidationError):
        await list_orders(client, page=0)


@respx.mock
async def test_get_order_success(mock_client):
    data = load_fixture("order_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/orders/101").respond(
        status_code=200,
        json=data,
    )

    detail = await get_order(mock_client, order_id=101)
    assert isinstance(detail, OrderDetail)
    assert detail.id == 101
    assert detail.status == "processing"
    assert len(detail.line_items) == 1
    assert detail.line_items[0].name == "Wireless Noise-Canceling Headphones"
    assert detail.billing.full_name == "John D."
    assert detail.billing.address_1 == "[REDACTED]"
    assert detail.billing.city == "Seattle"
    assert detail.billing.email == "j***@example.com"
    assert detail.billing.phone == "***-***-**67"


@respx.mock
async def test_get_order_not_found(mock_client):
    respx.get("https://store.example.com/wp-json/wc/v3/orders/999").respond(
        status_code=404,
        json={"code": "order_not_found"},
    )

    with pytest.raises(NotFoundError):
        await get_order(mock_client, order_id=999)


@respx.mock
async def test_search_orders(mock_client):
    data = load_fixture("orders_list_sample.json")
    route = respx.get("https://store.example.com/wp-json/wc/v3/orders").respond(
        status_code=200,
        headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
        json=[data[0]],
    )

    res = await search_orders(mock_client, query="John")
    assert len(res.items) == 1
    assert res.items[0].id == 101
    assert route.calls.last.request.url.params["search"] == "John"


async def test_search_orders_empty_query(mock_client):
    with pytest.raises(ValidationError):
        await search_orders(mock_client, query="")


@respx.mock
async def test_list_products(mock_client):
    data = load_fixture("products_list_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/products").respond(
        status_code=200,
        headers={"X-WP-Total": "3", "X-WP-TotalPages": "1"},
        json=data,
    )

    result = await list_products(mock_client, stock_status="instock")
    assert len(result.items) == 3
    assert isinstance(result.items[0], ProductSummary)
    assert result.items[0].sku == "HEADPHONE-NC"


@respx.mock
async def test_get_product(mock_client):
    data = load_fixture("product_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/products/401").respond(
        status_code=200,
        json=data,
    )

    prod = await get_product(mock_client, product_id=401)
    assert isinstance(prod, ProductSummary)
    assert prod.id == 401
    assert prod.price == "99.99"


@respx.mock
async def test_search_products(mock_client):
    data = load_fixture("products_list_sample.json")
    route = respx.get("https://store.example.com/wp-json/wc/v3/products").respond(
        status_code=200,
        headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"},
        json=[data[1]],
    )

    res = await search_products(mock_client, sku="KEYBOARD-RGB")
    assert len(res.items) == 1
    assert res.items[0].id == 402
    assert route.calls.last.request.url.params["sku"] == "KEYBOARD-RGB"


@respx.mock
async def test_get_stock_by_id(mock_client):
    data = load_fixture("product_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/products/401").respond(
        status_code=200,
        json=data,
    )

    stock = await get_stock(mock_client, product_id_or_sku=401)
    assert isinstance(stock, StockInfo)
    assert stock.product_id == 401
    assert stock.stock_quantity == 25
    assert stock.low_stock is False


@respx.mock
async def test_get_stock_by_sku(mock_client):
    data = load_fixture("products_list_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/products").respond(
        status_code=200,
        json=[data[1]],
    )

    stock = await get_stock(mock_client, product_id_or_sku="KEYBOARD-RGB")
    assert isinstance(stock, StockInfo)
    assert stock.sku == "KEYBOARD-RGB"
    assert stock.stock_quantity == 3
    assert stock.low_stock is True  # <= 5 threshold


@respx.mock
async def test_list_low_stock(mock_client):
    data = load_fixture("products_list_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/products").respond(
        status_code=200,
        headers={"X-WP-Total": "3", "X-WP-TotalPages": "1"},
        json=data,
    )

    low_stock_page = await list_low_stock(mock_client, threshold=5)
    # data[1] (qty 3) and data[2] (qty 0, outofstock) should be marked low_stock
    assert len(low_stock_page.items) == 2
    assert low_stock_page.items[0].product_id == 402
    assert low_stock_page.items[1].product_id == 403


@respx.mock
async def test_get_store_status(mock_client):
    data = load_fixture("system_status_sample.json")
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=200,
        json=data,
    )

    status = await get_store_status(mock_client)
    assert isinstance(status, StoreStatus)
    assert status.connected is True
    assert status.wp_version == "6.4.3"
    assert status.wc_version == "8.5.1"
    assert status.currency == "USD"
    assert status.currency_symbol == "$"


def test_map_exception_to_tool_error():
    auth_err = map_exception_to_tool_error(AuthError("Unauthorized", status_code=401))
    assert auth_err.code == "AUTH_FAILED"
    assert auth_err.retryable is False

    nf_err = map_exception_to_tool_error(NotFoundError("Item missing"))
    assert nf_err.code == "NOT_FOUND"
    assert nf_err.retryable is False

    rl_err = map_exception_to_tool_error(RateLimitedError("Too many calls", retry_after=30.0))
    assert rl_err.code == "RATE_LIMITED"
    assert rl_err.retryable is True
    assert rl_err.retry_after == 30.0

    up_err = map_exception_to_tool_error(UpstreamError("Bad Gateway", status_code=502))
    assert up_err.code == "UPSTREAM_ERROR"
    assert up_err.retryable is True

    val_err = map_exception_to_tool_error(ValidationError("Invalid param"))
    assert val_err.code == "INVALID_INPUT"
    assert val_err.retryable is False

    generic_err = map_exception_to_tool_error(ValueError("Some internal failure"))
    assert generic_err.code == "INTERNAL_ERROR"


@respx.mock
async def test_tool_edge_cases_and_validations(mock_client):
    # ValidationError on negative page/per_page
    with pytest.raises(ValidationError):
        await list_orders(mock_client, page=-1)
    with pytest.raises(ValidationError):
        await list_orders(mock_client, per_page=0)
    with pytest.raises(ValidationError):
        await list_orders(mock_client, before="invalid-date")
    with pytest.raises(ValidationError):
        await list_orders(mock_client, customer_id=-5)

    with pytest.raises(ValidationError):
        await get_order(mock_client, order_id=0)

    with pytest.raises(ValidationError):
        await search_orders(mock_client, query="")
    with pytest.raises(ValidationError):
        await search_orders(mock_client, query="test", page=0)
    with pytest.raises(ValidationError):
        await search_orders(mock_client, query="test", per_page=0)

    with pytest.raises(ValidationError):
        await list_products(mock_client, page=0)
    with pytest.raises(ValidationError):
        await list_products(mock_client, per_page=0)
    with pytest.raises(ValidationError):
        await list_products(mock_client, stock_status="invalid_stock_status")

    with pytest.raises(ValidationError):
        await get_product(mock_client, product_id=-1)

    with pytest.raises(ValidationError):
        await search_products(mock_client, page=0)
    with pytest.raises(ValidationError):
        await search_products(mock_client, per_page=0)
    with pytest.raises(ValidationError):
        await search_products(mock_client)

    with pytest.raises(ValidationError):
        await get_stock(mock_client, product_id_or_sku="   ")

    with pytest.raises(ValidationError):
        await list_low_stock(mock_client, threshold=-1)
    with pytest.raises(ValidationError):
        await list_low_stock(mock_client, page=0)
    with pytest.raises(ValidationError):
        await list_low_stock(mock_client, per_page=0)

    # Product not found
    respx.get("https://store.example.com/wp-json/wc/v3/products/999").respond(
        status_code=404,
        json={"code": "woocommerce_rest_product_invalid_id", "message": "Invalid ID."},
    )
    with pytest.raises(NotFoundError):
        await get_product(mock_client, product_id=999)

    # SKU not found in stock search
    respx.get("https://store.example.com/wp-json/wc/v3/products").respond(
        status_code=200,
        json=[],
    )
    with pytest.raises(NotFoundError):
        await get_stock(mock_client, product_id_or_sku="UNKNOWN-SKU-XYZ")
