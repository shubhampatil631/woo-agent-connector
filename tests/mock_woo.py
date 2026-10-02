"""Mock WooCommerce server for testing and demonstrations.

Provides configurable simulation for:
- 429 Too Many Requests (with Retry-After headers for N attempts)
- 503 Service Unavailable (intermittent failure simulation)
- Authentication checks (Basic auth and query parameters)
- Order and Product pagination (X-WP-Total, X-WP-TotalPages)
- Order details with billing, shipping, line items
- Low stock and inventory filtering
- System status inspection
"""

import argparse
import base64
import logging
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("mock_woo")

app = FastAPI(title="Mock WooCommerce API")


class MockWooState:
    def __init__(self) -> None:
        self.rate_limit_429_count: int = 0
        self.retry_after_seconds: float = 0.5
        self.fail_503_count: int = 0
        self.require_auth: bool = True
        self.expected_key: str = "ck_test_mock_key"
        self.expected_secret: str = "cs_test_mock_secret"
        self.reset_data()

    def reset_data(self) -> None:
        """Initialize mock products and orders."""
        self.products: list[dict[str, Any]] = [
            {
                "id": 101,
                "name": "Leather Laptop Sleeve",
                "sku": "SLEEVE-LTH-01",
                "type": "simple",
                "status": "publish",
                "price": "49.99",
                "manage_stock": True,
                "stock_status": "instock",
                "stock_quantity": 4,  # low stock (< 5)
                "backorders": "no",
                "low_stock_amount": 5,
            },
            {
                "id": 102,
                "name": "Mechanical Keyboard",
                "sku": "KB-MECH-RGB",
                "type": "simple",
                "status": "publish",
                "price": "129.99",
                "manage_stock": True,
                "stock_status": "instock",
                "stock_quantity": 25,
                "backorders": "no",
                "low_stock_amount": 5,
            },
            {
                "id": 103,
                "name": "Wireless Mouse",
                "sku": "MOUSE-WL-BLK",
                "type": "simple",
                "status": "publish",
                "price": "39.99",
                "manage_stock": True,
                "stock_status": "outofstock",
                "stock_quantity": 0,
                "backorders": "notify",
                "low_stock_amount": 3,
            },
            {
                "id": 104,
                "name": "Ergonomic Desk Mat",
                "sku": "MAT-DESK-XL",
                "type": "simple",
                "status": "publish",
                "price": "29.99",
                "manage_stock": False,
                "stock_status": "instock",
                "stock_quantity": None,
                "backorders": "no",
                "low_stock_amount": None,
            },
        ]

        # Generate 25 orders to test multi-page pagination (3 pages at per_page=10)
        self.orders: list[dict[str, Any]] = []
        statuses = ["processing", "completed", "on-hold", "pending", "failed", "refunded"]
        for i in range(1, 26):
            status = statuses[(i - 1) % len(statuses)]
            self.orders.append(
                {
                    "id": 1000 + i,
                    "number": str(1000 + i),
                    "status": status,
                    "date_created": f"2026-09-{(i % 28) + 1:02d}T10:00:00",
                    "total": f"{49.99 * ((i % 3) + 1):.2f}",
                    "currency": "INR",
                    "customer_id": (i % 5) + 1,
                    "payment_method": "razorpay",
                    "shipping_total": "10.00",
                    "discount_total": "5.00" if i % 2 == 0 else "0.00",
                    "line_items": [
                        {
                            "id": 200 + i,
                            "product_id": 101,
                            "variation_id": 0,
                            "name": "Leather Laptop Sleeve",
                            "sku": "SLEEVE-LTH-01",
                            "quantity": (i % 2) + 1,
                            "total": f"{49.99 * ((i % 2) + 1):.2f}",
                        }
                    ],
                    "refunds": [
                        {"id": 900 + i, "reason": "Customer request", "total": "-20.00"}
                    ]
                    if status == "refunded"
                    else [],
                    "billing": {
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "email": f"customer{i}@example.com",
                        "phone": f"+9198765432{i:02d}",
                        "address_1": "123 Tech Residency, 4th Block",
                        "city": "Bengaluru",
                        "state": "KA",
                        "postcode": "560001",
                        "country": "IN",
                    },
                    "shipping": {
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "address_1": "123 Tech Residency, 4th Block",
                        "city": "Bengaluru",
                        "state": "KA",
                        "postcode": "560001",
                        "country": "IN",
                    },
                }
            )


state = MockWooState()


def check_auth(request: Request, auth_header: str | None = None) -> bool:
    """Validate Basic Auth or query param credentials."""
    if not state.require_auth:
        return True

    # 1. Check query params (http dev flow)
    query_key = request.query_params.get("consumer_key")
    query_secret = request.query_params.get("consumer_secret")
    if query_key and query_secret:
        return query_key == state.expected_key and query_secret == state.expected_secret

    # 2. Check Basic Auth header
    if auth_header and auth_header.startswith("Basic "):
        try:
            raw = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            if ":" in raw:
                u, p = raw.split(":", 1)
                return u == state.expected_key and p == state.expected_secret
        except Exception:
            return False

    return False


@app.middleware("http")
async def simulation_middleware(request: Request, call_next):
    # Simulate 429 Too Many Requests
    if state.rate_limit_429_count > 0:
        state.rate_limit_429_count -= 1
        return JSONResponse(
            status_code=429,
            content={
                "code": "woocommerce_rest_rate_limited",
                "message": "Too Many Requests",
            },
            headers={"Retry-After": str(state.retry_after_seconds)},
        )

    # Simulate 503 Service Unavailable
    if state.fail_503_count > 0:
        state.fail_503_count -= 1
        return JSONResponse(
            status_code=503,
            content={"code": "woocommerce_rest_service_unavailable", "message": "Upstream timeout"},
        )

    return await call_next(request)


@app.get("/wp-json")
async def root_discovery(request: Request, authorization: str | None = Header(None)):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})
    return {
        "name": "Mock WooCommerce Sandbox Store",
        "description": "Fictional store for testing Agent Studio connectors",
        "namespaces": ["wc/v3"],
        "authentication": {"oauth": {"scope": "read"}},
    }


@app.get("/wp-json/wc/v3/system_status")
async def system_status(request: Request, authorization: str | None = Header(None)):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})
    return {
        "environment": {
            "site_title": "Mock WooCommerce Sandbox Store",
            "version": "8.5.0",
            "wp_version": "6.4.3",
            "secure_connection": True,
        },
        "settings": {
            "currency": "INR",
            "currency_symbol": "₹",
        },
    }


@app.get("/wp-json/wc/v3/orders")
async def list_orders(
    request: Request,
    authorization: str | None = Header(None),
    status: str | None = Query(None),
    customer: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})

    filtered = state.orders
    if status:
        statuses = [s.strip().lower() for s in status.split(",")]
        filtered = [o for o in filtered if o["status"].lower() in statuses]
    if customer:
        filtered = [o for o in filtered if o["customer_id"] == customer]
    if search:
        s_lower = search.lower()
        filtered = [
            o
            for o in filtered
            if s_lower in str(o["id"])
            or s_lower in o["billing"]["email"].lower()
            or s_lower in o["billing"]["first_name"].lower()
            or s_lower in o["billing"]["last_name"].lower()
        ]

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    items = filtered[start_idx:end_idx]

    return JSONResponse(
        content=items,
        headers={
            "X-WP-Total": str(total),
            "X-WP-TotalPages": str(total_pages),
        },
    )


@app.get("/wp-json/wc/v3/orders/{order_id}")
async def get_order(
    order_id: int, request: Request, authorization: str | None = Header(None)
):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})

    for o in state.orders:
        if o["id"] == order_id:
            return o
    return JSONResponse(
        status_code=404,
        content={"code": "woocommerce_rest_order_invalid_id", "message": "Invalid ID."},
    )


@app.get("/wp-json/wc/v3/products")
async def list_products(
    request: Request,
    authorization: str | None = Header(None),
    status: str | None = Query(None),
    sku: str | None = Query(None),
    stock_status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})

    filtered = state.products
    if status:
        filtered = [p for p in filtered if p["status"] == status]
    if sku:
        filtered = [p for p in filtered if p["sku"] == sku]
    if stock_status:
        filtered = [p for p in filtered if p["stock_status"] == stock_status]
    if search:
        s_lower = search.lower()
        filtered = [
            p
            for p in filtered
            if s_lower in p["name"].lower() or s_lower in (p["sku"] or "").lower()
        ]

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    items = filtered[start_idx:end_idx]

    return JSONResponse(
        content=items,
        headers={
            "X-WP-Total": str(total),
            "X-WP-TotalPages": str(total_pages),
        },
    )


@app.get("/wp-json/wc/v3/products/{product_id}")
async def get_product(
    product_id: int, request: Request, authorization: str | None = Header(None)
):
    if not check_auth(request, authorization):
        return JSONResponse(status_code=401, content={"code": "woocommerce_rest_cannot_view"})

    for p in state.products:
        if p["id"] == product_id:
            return p
    return JSONResponse(
        status_code=404,
        content={"code": "woocommerce_rest_product_invalid_id", "message": "Invalid product ID."},
    )


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Mock WooCommerce API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8081, help="Port to bind")
    args = parser.parse_args()
    print(f"Starting Mock WooCommerce server on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
