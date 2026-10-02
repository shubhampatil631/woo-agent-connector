"""Business logic and transport-agnostic read primitives for Agent Studio."""

from datetime import datetime
from typing import Any

from woo_connector.client import (
    AuthError,
    NotFoundError,
    RateLimitedError,
    UpstreamError,
    ValidationError,
    WooClient,
)
from woo_connector.config import PIIMode
from woo_connector.models import (
    Address,
    LineItem,
    OrderDetail,
    OrderStatus,
    OrderSummary,
    PaginatedResult,
    ProductSummary,
    RefundItem,
    StockInfo,
    StockStatus,
    StoreStatus,
    ToolError,
)
from woo_connector.redact import (
    redact_address,
    redact_customer_ref,
)


def map_exception_to_tool_error(exc: Exception) -> ToolError:
    """Map any connector exception into an actionable, structured ToolError."""
    if isinstance(exc, AuthError):
        return ToolError(
            code="AUTH_FAILED",
            message=exc.agent_message,
            retryable=False,
        )
    if isinstance(exc, NotFoundError):
        return ToolError(
            code="NOT_FOUND",
            message=exc.agent_message,
            retryable=False,
        )
    if isinstance(exc, RateLimitedError):
        return ToolError(
            code="RATE_LIMITED",
            message=exc.agent_message,
            retryable=True,
            retry_after=exc.retry_after,
        )
    if isinstance(exc, UpstreamError):
        return ToolError(
            code="UPSTREAM_ERROR",
            message=exc.agent_message,
            retryable=True,
        )
    if isinstance(exc, ValidationError):
        return ToolError(
            code="INVALID_INPUT",
            message=exc.agent_message,
            retryable=False,
        )
    return ToolError(
        code="INTERNAL_ERROR",
        message=f"An unexpected connector error occurred: {exc}",
        retryable=False,
    )


def _validate_date_param(param_name: str, value: str | None) -> None:
    if not value:
        return
    clean_val = value.strip()
    try:
        if "T" in clean_val:
            datetime.fromisoformat(clean_val.replace("Z", "+00:00"))
        else:
            datetime.strptime(clean_val, "%Y-%m-%d")
    except ValueError as e:
        raise ValidationError(
            f"Invalid format for '{param_name}': expected ISO 8601 string "
            "(e.g. '2026-10-01T00:00:00Z' or '2026-10-01')"
        ) from e


def _parse_order_summary(raw: dict[str, Any], mode: PIIMode) -> OrderSummary:
    billing = raw.get("billing") or {}
    email = billing.get("email")
    customer_id = raw.get("customer_id")
    customer_ref = redact_customer_ref(customer_id, email=email, mode=mode)

    line_items = raw.get("line_items") or []
    item_count = sum(int(item.get("quantity", 1)) for item in line_items)

    return OrderSummary(
        id=int(raw.get("id", 0)),
        number=str(raw.get("number", raw.get("id", ""))),
        status=str(raw.get("status", "unknown")),
        date_created=str(raw.get("date_created", "")),
        total=str(raw.get("total", "0.00")),
        currency=str(raw.get("currency", "USD")),
        item_count=item_count,
        customer_ref=customer_ref,
        payment_method=str(raw.get("payment_method_title") or raw.get("payment_method") or "N/A"),
    )


def _parse_order_detail(raw: dict[str, Any], mode: PIIMode) -> OrderDetail:
    summary = _parse_order_summary(raw, mode)

    line_items = [
        LineItem(
            product_id=int(item.get("product_id", 0)),
            variation_id=item.get("variation_id") or None,
            name=str(item.get("name", "Unknown Item")),
            sku=item.get("sku") or None,
            quantity=int(item.get("quantity", 1)),
            total=str(item.get("total", "0.00")),
        )
        for item in (raw.get("line_items") or [])
    ]

    refunds = [
        RefundItem(
            id=int(ref.get("id", 0)),
            reason=ref.get("reason") or None,
            total=str(ref.get("total", "0.00")),
        )
        for ref in (raw.get("refunds") or [])
    ]

    billing_data = redact_address(raw.get("billing"), mode=mode)
    shipping_data = redact_address(raw.get("shipping"), mode=mode)

    return OrderDetail(
        id=summary.id,
        number=summary.number,
        status=summary.status,
        date_created=summary.date_created,
        total=summary.total,
        currency=summary.currency,
        item_count=summary.item_count,
        customer_ref=summary.customer_ref,
        payment_method=summary.payment_method,
        line_items=line_items,
        shipping_total=str(raw.get("shipping_total", "0.00")),
        discount_total=str(raw.get("discount_total", "0.00")),
        refunds=refunds,
        notes_available=bool(raw.get("customer_note")),
        billing=Address(**billing_data),
        shipping=Address(**shipping_data),
    )


def _parse_product_summary(raw: dict[str, Any]) -> ProductSummary:
    return ProductSummary(
        id=int(raw.get("id", 0)),
        name=str(raw.get("name", "Unnamed Product")),
        sku=raw.get("sku") or None,
        type=str(raw.get("type", "simple")),
        status=str(raw.get("status", "publish")),
        price=str(raw.get("price") or raw.get("regular_price") or "0.00"),
        stock_status=str(raw.get("stock_status", "instock")),
        stock_quantity=raw.get("stock_quantity"),
        manage_stock=bool(raw.get("manage_stock", False)),
    )


async def list_orders(
    client: WooClient,
    status: str | None = None,
    after: str | None = None,
    before: str | None = None,
    customer_id: int | None = None,
    page: int = 1,
    per_page: int = 50,
    pii_mode: PIIMode | None = None,
) -> PaginatedResult[OrderSummary]:
    """List orders with filtering by status, date range, and customer."""
    if page < 1:
        raise ValidationError("page must be an integer >= 1")
    if per_page < 1:
        raise ValidationError("per_page must be an integer >= 1")
    if customer_id is not None and customer_id < 1:
        raise ValidationError("customer_id must be a positive integer")

    params: dict[str, Any] = {}
    if status:
        status_clean = status.strip().lower()
        valid_statuses = [s.value for s in OrderStatus]
        if status_clean != "any" and status_clean not in valid_statuses:
            raise ValidationError(
                f"Invalid order status '{status}'. Valid options: {', '.join(valid_statuses)}"
            )
        params["status"] = status_clean

    if after:
        _validate_date_param("after", after)
        params["after"] = after
    if before:
        _validate_date_param("before", before)
        params["before"] = before
    if customer_id:
        params["customer"] = customer_id

    mode = pii_mode or client.config.pii_mode
    page_res = await client.get_page(
        "/wp-json/wc/v3/orders", params=params, page=page, per_page=per_page
    )

    items = [_parse_order_summary(item, mode) for item in page_res.items]
    return PaginatedResult(
        items=items,
        page=page_res.page,
        per_page=page_res.per_page,
        total=page_res.total,
        total_pages=page_res.total_pages,
        has_more=page_res.has_more,
    )


async def get_order(
    client: WooClient,
    order_id: int,
    pii_mode: PIIMode | None = None,
) -> OrderDetail:
    """Retrieve full details for a single order by ID with PII redaction."""
    if not isinstance(order_id, int) or order_id < 1:
        raise ValidationError("order_id must be a positive integer")

    mode = pii_mode or client.config.pii_mode
    data = await client.get(f"/wp-json/wc/v3/orders/{order_id}")
    if not isinstance(data, dict) or not data.get("id"):
        raise NotFoundError(f"Order #{order_id} not found")

    return _parse_order_detail(data, mode)


async def search_orders(
    client: WooClient,
    query: str,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
    pii_mode: PIIMode | None = None,
) -> PaginatedResult[OrderSummary]:
    """Search orders across order numbers and customer billing/shipping details."""
    q = (query or "").strip()
    if not q:
        raise ValidationError("Search query cannot be empty")
    if page < 1:
        raise ValidationError("page must be an integer >= 1")
    if per_page < 1:
        raise ValidationError("per_page must be an integer >= 1")

    params: dict[str, Any] = {"search": q}
    if status:
        status_clean = status.strip().lower()
        if status_clean != "any" and status_clean not in [s.value for s in OrderStatus]:
            raise ValidationError(f"Invalid order status '{status}'")
        params["status"] = status_clean

    mode = pii_mode or client.config.pii_mode
    page_res = await client.get_page(
        "/wp-json/wc/v3/orders", params=params, page=page, per_page=per_page
    )

    items = [_parse_order_summary(item, mode) for item in page_res.items]
    return PaginatedResult(
        items=items,
        page=page_res.page,
        per_page=page_res.per_page,
        total=page_res.total,
        total_pages=page_res.total_pages,
        has_more=page_res.has_more,
    )


async def list_products(
    client: WooClient,
    status: str | None = None,
    stock_status: str | None = None,
    category: int | str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> PaginatedResult[ProductSummary]:
    """List products with optional stock status and category filters."""
    if page < 1:
        raise ValidationError("page must be >= 1")
    if per_page < 1:
        raise ValidationError("per_page must be >= 1")

    params: dict[str, Any] = {}
    if status:
        params["status"] = status.strip().lower()
    if stock_status:
        stock_clean = stock_status.strip().lower()
        valid_stock = [s.value for s in StockStatus]
        if stock_clean not in valid_stock:
            raise ValidationError(
                f"Invalid stock_status '{stock_status}'. Valid: {', '.join(valid_stock)}"
            )
        params["stock_status"] = stock_clean
    if category is not None:
        params["category"] = str(category).strip()

    page_res = await client.get_page(
        "/wp-json/wc/v3/products", params=params, page=page, per_page=per_page
    )

    items = [_parse_product_summary(item) for item in page_res.items]
    return PaginatedResult(
        items=items,
        page=page_res.page,
        per_page=page_res.per_page,
        total=page_res.total,
        total_pages=page_res.total_pages,
        has_more=page_res.has_more,
    )


async def get_product(client: WooClient, product_id: int) -> ProductSummary:
    """Retrieve summary information for a single product by ID."""
    if not isinstance(product_id, int) or product_id < 1:
        raise ValidationError("product_id must be a positive integer")

    data = await client.get(f"/wp-json/wc/v3/products/{product_id}")
    if not isinstance(data, dict) or not data.get("id"):
        raise NotFoundError(f"Product #{product_id} not found")

    return _parse_product_summary(data)


async def search_products(
    client: WooClient,
    query: str | None = None,
    sku: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> PaginatedResult[ProductSummary]:
    """Search products by keyword or SKU."""
    if not query and not sku:
        raise ValidationError("Either 'query' or 'sku' must be provided for product search")
    if page < 1:
        raise ValidationError("page must be >= 1")
    if per_page < 1:
        raise ValidationError("per_page must be >= 1")

    params: dict[str, Any] = {}
    if sku:
        params["sku"] = sku.strip()
    if query:
        params["search"] = query.strip()

    page_res = await client.get_page(
        "/wp-json/wc/v3/products", params=params, page=page, per_page=per_page
    )

    items = [_parse_product_summary(item) for item in page_res.items]
    return PaginatedResult(
        items=items,
        page=page_res.page,
        per_page=page_res.per_page,
        total=page_res.total,
        total_pages=page_res.total_pages,
        has_more=page_res.has_more,
    )


async def get_stock(client: WooClient, product_id_or_sku: int | str) -> StockInfo:
    """Check stock and inventory status for a specific product ID or SKU."""
    target = str(product_id_or_sku).strip()
    if not target:
        raise ValidationError("product_id_or_sku must be specified")

    product_data = None
    if target.isdigit():
        try:
            data = await client.get(f"/wp-json/wc/v3/products/{target}")
            if isinstance(data, dict) and data.get("id"):
                product_data = data
        except NotFoundError:
            pass

    if not product_data:
        # Search by SKU
        search_res = await client.get("/wp-json/wc/v3/products", params={"sku": target})
        if isinstance(search_res, list) and search_res:
            product_data = search_res[0]

    if not product_data:
        raise NotFoundError(f"No product found matching '{product_id_or_sku}'")

    stock_qty = product_data.get("stock_quantity")
    manage_stock = bool(product_data.get("manage_stock", False))
    stock_status = str(product_data.get("stock_status", "instock"))

    is_low_stock = False
    if manage_stock and stock_qty is not None:
        is_low_stock = stock_qty <= 5
    elif stock_status == "outofstock":
        is_low_stock = True

    return StockInfo(
        product_id=int(product_data["id"]),
        sku=product_data.get("sku") or None,
        stock_status=stock_status,
        stock_quantity=stock_qty,
        low_stock=is_low_stock,
        backorders=product_data.get("backorders", False),
    )


async def list_low_stock(
    client: WooClient,
    threshold: int = 5,
    page: int = 1,
    per_page: int = 50,
) -> PaginatedResult[StockInfo]:
    """Find products with stock quantities at or below the given threshold."""
    if threshold < 0:
        raise ValidationError("threshold must be >= 0")
    if page < 1:
        raise ValidationError("page must be >= 1")
    if per_page < 1:
        raise ValidationError("per_page must be >= 1")

    # Fetch products page
    page_res = await client.get_page("/wp-json/wc/v3/products", page=page, per_page=per_page)

    low_stock_items: list[StockInfo] = []
    for raw in page_res.items:
        manage_stock = bool(raw.get("manage_stock", False))
        stock_qty = raw.get("stock_quantity")
        stock_status = str(raw.get("stock_status", "instock"))

        is_low = False
        if (manage_stock and stock_qty is not None and stock_qty <= threshold) or (
            stock_status == "outofstock"
        ):
            is_low = True

        if is_low:
            low_stock_items.append(
                StockInfo(
                    product_id=int(raw["id"]),
                    sku=raw.get("sku") or None,
                    stock_status=stock_status,
                    stock_quantity=stock_qty,
                    low_stock=True,
                    backorders=raw.get("backorders", False),
                )
            )

    return PaginatedResult(
        items=low_stock_items,
        page=page_res.page,
        per_page=page_res.per_page,
        total=len(low_stock_items),
        total_pages=page_res.total_pages,
        has_more=page_res.has_more,
    )


async def get_store_status(client: WooClient) -> StoreStatus:
    """Retrieve connectivity, WordPress/WooCommerce versions, and currency settings."""
    data = await client.get("/wp-json/wc/v3/system_status")
    if not isinstance(data, dict):
        raise UpstreamError("Invalid system status response received from store")

    environment = data.get("environment") or {}
    settings_data = data.get("settings") or {}

    return StoreStatus(
        connected=True,
        store_url=str(client.config.base_url),
        wp_version=environment.get("wp_version"),
        wc_version=environment.get("version"),
        currency=settings_data.get("currency"),
        currency_symbol=settings_data.get("currency_symbol"),
        timezone=settings_data.get("timezone"),
    )
