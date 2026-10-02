"""FastMCP server entrypoint for WooCommerce Agent Studio connector."""

import argparse
import asyncio
import hmac
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from woo_connector.auth import verify_credentials
from woo_connector.client import WooClient
from woo_connector.config import Settings, settings
from woo_connector.tools import (
    get_order as tool_get_order,
)
from woo_connector.tools import (
    get_product as tool_get_product,
)
from woo_connector.tools import (
    get_stock as tool_get_stock,
)
from woo_connector.tools import (
    get_store_status as tool_get_store_status,
)
from woo_connector.tools import (
    list_low_stock as tool_list_low_stock,
)
from woo_connector.tools import (
    list_orders as tool_list_orders,
)
from woo_connector.tools import (
    list_products as tool_list_products,
)
from woo_connector.tools import (
    map_exception_to_tool_error,
)
from woo_connector.tools import (
    search_orders as tool_search_orders,
)
from woo_connector.tools import (
    search_products as tool_search_products,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("woo-mcp-server")

mcp = FastMCP("woocommerce-connector")


def get_client() -> WooClient:
    """Return a managed WooClient instance."""
    return WooClient()


# =====================================================================
# MCP Resources
# =====================================================================


@mcp.resource("woo://store/status")
async def store_status_resource() -> str:
    """Store connectivity, versions, and active currency metadata."""
    async with get_client() as client:
        try:
            status = await tool_get_store_status(client)
            return status.model_dump_json(indent=2)
        except Exception as exc:
            err = map_exception_to_tool_error(exc)
            return err.model_dump_json(indent=2)


@mcp.resource("woo://docs/capabilities")
async def capabilities_resource() -> str:
    """Serves the full connector capabilities, limits, and read-only boundaries."""
    doc_path = Path(__file__).parent.parent.parent / "docs" / "CAPABILITIES.md"
    if doc_path.exists():
        return doc_path.read_text(encoding="utf-8")
    return "Capabilities document not found on disk."


# =====================================================================
# MCP Tools (LLM-Optimized Read Primitives)
# =====================================================================


@mcp.tool(
    name="list_orders",
    description=(
        "List WooCommerce orders with filtering by status, date range, or customer. "
        "Returns compact OrderSummary items and pagination metadata (total, total_pages, "
        "has_more). Use this to inspect recent store orders or query orders in a specific "
        "lifecycle state (e.g., 'processing', 'completed', 'pending', 'on-hold', 'cancelled', "
        "'refunded', 'failed'). "
        "DO NOT use this to search by customer name or keyword (use search_orders instead)."
    ),
)
async def list_orders(
    status: str | None = None,
    after: str | None = None,
    before: str | None = None,
    customer_id: int | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """List store orders with filtering and pagination."""
    async with get_client() as client:
        try:
            result = await tool_list_orders(
                client=client,
                status=status,
                after=after,
                before=before,
                customer_id=customer_id,
                page=page,
                per_page=per_page,
            )
            return result.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="get_order",
    description=(
        "Retrieve full details for a single known WooCommerce order by integer order ID. "
        "Returns purchased line items, variation IDs, pricing, refund history, and "
        "privacy-redacted billing/shipping addresses. "
        "Use when you need line item details or delivery addresses for a specific order ID."
    ),
)
async def get_order(order_id: int) -> dict[str, Any]:
    """Get full details of a specific order."""
    async with get_client() as client:
        try:
            detail = await tool_get_order(client=client, order_id=order_id)
            return detail.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="search_orders",
    description=(
        "Search orders by text query matching order numbers, customer names, emails, "
        "or billing and shipping address fields. "
        "Returns matching OrderSummary items with pagination. "
        "Use when finding orders by partial query text or customer name."
    ),
)
async def search_orders(
    query: str,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Search orders across order numbers and customer details."""
    async with get_client() as client:
        try:
            result = await tool_search_orders(
                client=client,
                query=query,
                status=status,
                page=page,
                per_page=per_page,
            )
            return result.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="list_products",
    description=(
        "List products in the store catalog with optional status, stock_status "
        "('instock', 'outofstock', 'onbackorder'), and category filters. "
        "Returns ProductSummary items with price and stock status. "
        "DO NOT use this for text keyword searching (use search_products instead)."
    ),
)
async def list_products(
    status: str | None = None,
    stock_status: str | None = None,
    category: int | str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """List catalog products with filtering and pagination."""
    async with get_client() as client:
        try:
            result = await tool_list_products(
                client=client,
                status=status,
                stock_status=stock_status,
                category=category,
                page=page,
                per_page=per_page,
            )
            return result.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="get_product",
    description=(
        "Retrieve product metadata, SKU, type, pricing, and stock status for a single "
        "known product by integer product ID."
    ),
)
async def get_product(product_id: int) -> dict[str, Any]:
    """Get metadata for a single product by ID."""
    async with get_client() as client:
        try:
            product = await tool_get_product(client=client, product_id=product_id)
            return product.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="search_products",
    description=(
        "Search catalog products by text keyword (matching title/description) or exact SKU. "
        "Returns matching ProductSummary items with pricing and stock availability."
    ),
)
async def search_products(
    query: str | None = None,
    sku: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Search products by keyword or SKU."""
    async with get_client() as client:
        try:
            result = await tool_search_products(
                client=client,
                query=query,
                sku=sku,
                page=page,
                per_page=per_page,
            )
            return result.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="get_stock",
    description=(
        "Check real-time stock levels, stock status ('instock', 'outofstock'), "
        "and low-stock alerts for a specific product by integer ID or SKU string."
    ),
)
async def get_stock(product_id_or_sku: str) -> dict[str, Any]:
    """Get inventory level and stock status for a product or SKU."""
    async with get_client() as client:
        try:
            stock = await tool_get_stock(client=client, product_id_or_sku=product_id_or_sku)
            return stock.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="list_low_stock",
    description=(
        "List products currently at or below the specified stock quantity threshold "
        "(default: 5 units) or marked as out-of-stock. "
        "Use this tool to identify inventory needing restocking."
    ),
)
async def list_low_stock(
    threshold: int = 5,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """List low-stock and out-of-stock items."""
    async with get_client() as client:
        try:
            result = await tool_list_low_stock(
                client=client,
                threshold=threshold,
                page=page,
                per_page=per_page,
            )
            return result.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


@mcp.tool(
    name="get_store_status",
    description=(
        "Check WooCommerce store connection health, WordPress/WooCommerce software versions, "
        "store currency, currency symbol, and timezone configuration."
    ),
)
async def get_store_status() -> dict[str, Any]:
    """Check store connection health and software versions."""
    async with get_client() as client:
        try:
            status = await tool_get_store_status(client)
            return status.model_dump()
        except Exception as exc:
            return map_exception_to_tool_error(exc).model_dump()


# =====================================================================
# Startup Verification
# =====================================================================


async def run_startup_check(config: Settings = settings) -> None:
    """Validate credentials on startup and fail fast if invalid or violating strict read-only."""
    logger.info("Verifying WooCommerce store credentials on startup (%s)...", config.base_url)
    res = await verify_credentials(config)

    if not res.success:
        logger.error(
            "STARTUP FAILED: Cannot connect to WooCommerce (HTTP %d): %s",
            res.status_code,
            res.message,
        )
        sys.exit(1)

    if config.strict_readonly and res.permissions != "read":
        logger.error(
            "STARTUP FAILED: STRICT_READONLY=true is set, but provided credentials "
            "have '%s' permissions.",
            res.permissions,
        )
        sys.exit(1)

    logger.info("Startup check passed. Connected to store (permissions: %s).", res.permissions)


# =====================================================================
# HTTP Transport Auth Middleware
# =====================================================================


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Constant-time token authentication middleware for HTTP transport."""

    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if self.api_key:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized: Missing Bearer token in Authorization header"},
                )

            token = auth_header.removeprefix("Bearer ").strip()
            if not hmac.compare_digest(token, self.api_key):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized: Invalid connector API key"},
                )

        return await call_next(request)


# =====================================================================
# Entrypoint CLI
# =====================================================================


def main():
    """Main entrypoint supporting stdio and streamable HTTP transports."""
    parser = argparse.ArgumentParser(description="WooCommerce Agent Studio FastMCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol for MCP server (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address for HTTP/SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number for HTTP/SSE transport (default: 8000)",
    )
    parser.add_argument(
        "--skip-startup-check",
        action="store_true",
        help="Skip startup credential verification against store",
    )
    args = parser.parse_args()

    if not args.skip_startup_check and os.getenv("WOO_SKIP_STARTUP_CHECK") != "1":
        asyncio.run(run_startup_check(settings))

    if args.transport in ("http", "sse"):
        logger.info("Starting FastMCP server over HTTP/SSE on %s:%d...", args.host, args.port)
        # Configure SSE app with optional Bearer token auth middleware
        sse_app = mcp.sse_app()
        if settings.connector_api_key:
            sse_app.add_middleware(BearerAuthMiddleware, api_key=settings.connector_api_key)

        import uvicorn
        uvicorn.run(sse_app, host=args.host, port=args.port)
    else:
        logger.info("Starting FastMCP server over stdio transport...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
