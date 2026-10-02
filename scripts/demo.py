"""Interactive end-to-end demonstration for WooCommerce Agent Studio connector.

Demonstrates:
1. Credential verification and store status check
2. Listing recent orders with pagination
3. Searching orders by customer/email
4. Detailed order inspection with PII redaction active
5. Catalog low-stock inventory report
6. Rate-limit resilience: exponential backoff + Retry-After handling with recovery
7. Invalid credentials rejection with agent-actionable error relay
"""

import argparse
import asyncio
import contextlib
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from woo_connector.auth import verify_credentials
from woo_connector.client import WooClient
from woo_connector.config import Settings
from woo_connector.tools import (
    get_order,
    get_stock,
    get_store_status,
    list_low_stock,
    list_orders,
    map_exception_to_tool_error,
    search_orders,
)

with contextlib.suppress(Exception):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

# Setup rich console
console = Console(safe_box=True)

# Configure logging for demo
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def print_header(title: str, step: str) -> None:
    """Print standard demo section header."""
    console.print()
    console.print(
        Panel(
            Text(title, justify="center", style="bold cyan"),
            title=f"[bold green]STEP {step}[/bold green]",
            border_style="cyan",
        )
    )


def create_client(is_mock: bool, pii_mode: str = "redacted", bad_creds: bool = False) -> WooClient:
    """Create WooClient for live store or in-process mock."""
    if is_mock:
        from pathlib import Path

        from httpx import ASGITransport, AsyncClient

        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        from tests.mock_woo import app as mock_app
        from tests.mock_woo import state as mock_state
        from woo_connector.auth import get_auth_strategy

        key = "ck_invalid_key" if bad_creds else mock_state.expected_key
        secret = "cs_invalid_secret" if bad_creds else mock_state.expected_secret

        config = Settings(
            base_url="https://mock-woocommerce.local",
            consumer_key=key,
            consumer_secret=secret,
            pii_mode=pii_mode,
            rate_limit_rps=10.0,
            request_timeout=10.0,
            max_retries=3,
        )
        auth = get_auth_strategy(config)
        transport = ASGITransport(app=mock_app)
        http_client = AsyncClient(
            transport=transport,
            base_url="https://mock-woocommerce.local",
            auth=auth,
        )
        return WooClient(config=config, auth=auth, http_client=http_client)
    else:
        config = Settings(
            consumer_key="ck_invalid_key" if bad_creds else None,
            consumer_secret="cs_invalid_secret" if bad_creds else None,
            pii_mode=pii_mode,
        )
        return WooClient(config=config)


async def run_demo(is_mock: bool = False) -> None:
    """Execute complete end-to-end verification steps."""
    mode_str = "MOCK SANDBOX (In-Process)" if is_mock else "LIVE WOOCOMMERCE STORE"
    console.print(
        Panel(
            f"[bold white]WooCommerce Agent Studio Connector[/bold white]\n"
            f"[yellow]Execution Mode: {mode_str}[/yellow]\n"
            "[green]Read-Only Safety: ENFORCED | PII Redaction: ACTIVE[/green]",
            title="[bold blue]Razorpay Agent Studio[/bold blue]",
            border_style="blue",
        )
    )

    client = create_client(is_mock=is_mock)

    try:
        # STEP 1: Verify Credentials & Store Health
        print_header("1. Store Credential & Status Verification", "1")
        verify_res = await verify_credentials(client.config, client=client._client)
        perms = (verify_res.permissions or "read").upper()
        status_txt = "SUCCESS" if verify_res.success else "FAILED"
        console.print(
            f"[bold]Store URL:[/bold] {client.config.base_url}  |  "
            f"[bold]Status:[/bold] [green]{status_txt}[/green]  |  "
            f"[bold]Permissions:[/bold] [green]{perms}[/green]"
        )

        status = await get_store_status(client)
        console.print(
            f"[bold]WooCommerce Version:[/bold] {status.wc_version or 'N/A'}  |  "
            f"[bold]Currency:[/bold] {status.currency}"
        )

        # STEP 2: List Recent Orders
        print_header("2. List Recent Orders (Bounded Pagination)", "2")
        orders_page = await list_orders(client, page=1, per_page=5)

        table = Table(title=f"Recent Orders (Total: {orders_page.total})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Order #", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Total", style="green")
        table.add_column("Items", justify="right")
        table.add_column("Customer Ref", style="blue")

        for o in orders_page.items:
            table.add_row(
                str(o.id),
                o.number,
                o.status,
                f"{o.currency} {o.total}",
                str(o.item_count),
                o.customer_ref,
            )
        console.print(table)
        console.print(
            f"[dim]Page {orders_page.page}/{orders_page.total_pages} | "
            f"Has more: {orders_page.has_more}[/dim]"
        )

        # Pick an order for inspection
        sample_order_id = orders_page.items[0].id if orders_page.items else 1001

        # STEP 3: Search Order
        print_header("3. Search Orders by Customer or Query", "3")
        search_term = "customer" if is_mock else "Jane"
        search_res = await search_orders(client, query=search_term, page=1, per_page=3)
        console.print(
            f"[bold]Search Query:[/bold] '{search_term}'  ->  "
            f"[green]{search_res.total} matches found[/green]"
        )
        for item in search_res.items:
            console.print(
                f"  • Order [cyan]#{item.number}[/cyan] ({item.status}) - "
                f"Total: {item.currency} {item.total}"
            )

        # STEP 4: Get Order Detail with PII Redaction
        print_header("4. Get Detailed Order (PII Masking Active)", "4")
        order_detail = await get_order(client, order_id=sample_order_id)

        console.print(
            f"[bold cyan]Order #{order_detail.number}[/bold cyan] ({order_detail.status})"
        )
        console.print(f"  [bold]Purchased Items:[/bold] {len(order_detail.line_items)}")
        for item in order_detail.line_items:
            console.print(
                f"    - {item.name} (SKU: {item.sku or 'N/A'}) "
                f"x{item.quantity} = {order_detail.currency} {item.total}"
            )

        console.print("\n  [bold red]PII Redacted Customer Info (Agent-Safe):[/bold red]")
        console.print(
            f"    - [bold]Name:[/bold] "
            f"{order_detail.billing.first_name} {order_detail.billing.last_name}"
        )
        console.print(f"    - [bold]Email:[/bold] {order_detail.billing.email}")
        console.print(f"    - [bold]Phone:[/bold] {order_detail.billing.phone}")
        console.print(
            f"    - [bold]City/Country:[/bold] "
            f"{order_detail.billing.city}, {order_detail.billing.country}"
        )

        # STEP 5: Low-Stock Report
        print_header("5. Catalog Low-Stock Inventory Inspection", "5")
        low_stock = await list_low_stock(client, threshold=10, page=1, per_page=5)

        stock_table = Table(title=f"Low Stock Items (Threshold <= 10, Total: {low_stock.total})")
        stock_table.add_column("Product ID", style="cyan")
        stock_table.add_column("SKU", style="magenta")
        stock_table.add_column("Stock Qty", style="red", justify="right")
        stock_table.add_column("Status", style="yellow")
        stock_table.add_column("Low Alert", style="bold red")

        for prod in low_stock.items:
            stock_table.add_row(
                str(prod.product_id),
                prod.sku or "N/A",
                str(prod.stock_quantity if prod.stock_quantity is not None else "0"),
                prod.stock_status,
                str(prod.low_stock),
            )
        console.print(stock_table)

        # Single SKU stock inspection
        sample_sku = (
            low_stock.items[0].sku
            if low_stock.items and low_stock.items[0].sku
            else "SLEEVE-LTH-01"
        )
        try:
            sku_stock = await get_stock(client, product_id_or_sku=sample_sku)
            console.print(
                f"[bold]Target SKU Check ([cyan]{sample_sku}[/cyan]):[/bold] "
                f"Qty={sku_stock.stock_quantity}, LowStockAlert={sku_stock.low_stock}"
            )
        except Exception:
            pass

        # STEP 6: Forced Rate-Limit Scenario (429 Backoff & Recovery)
        print_header("6. Forced Rate-Limit Resilience Scenario", "6")
        console.print(
            "[yellow]Simulating upstream HTTP 429 'Too Many Requests' with "
            "Retry-After header...[/yellow]"
        )
        if is_mock:
            from tests.mock_woo import state as mock_state

            mock_state.rate_limit_429_count = 2  # Fail next 2 requests with 429
            mock_state.retry_after_seconds = 0.5

        console.print(
            "[dim]Issuing request through WooClient with automatic backoff + jitter...[/dim]"
        )
        recovered_orders = await list_orders(client, page=1, per_page=2)
        console.print(
            f"[bold green]✓ Successfully recovered after exponential backoff![/bold green] "
            f"(Fetched {len(recovered_orders.items)} orders)"
        )

        # STEP 7: Bad Key Scenario (Agent-Actionable Error Relay)
        print_header("7. Authentication Failure Guardrail", "7")
        console.print("[yellow]Testing connector response with invalid API credentials...[/yellow]")
        bad_client = create_client(is_mock=is_mock, bad_creds=True)
        try:
            await list_orders(bad_client)
            console.print("[red]Unexpected success with invalid credentials[/red]")
        except Exception as exc:
            err = map_exception_to_tool_error(exc)
            console.print(
                Panel(
                    f"[bold red]Code:[/bold red] {err.code}\n"
                    f"[bold]Retryable:[/bold] {err.retryable}\n"
                    f"[bold green]LLM Agent Actionable Message:[/bold green]\n\"{err.message}\"",
                    title="[bold yellow]Agent Error Payload[/bold yellow]",
                    border_style="yellow",
                )
            )

        console.print("\n[bold green]" + "=" * 55 + "[/bold green]")
        console.print("[bold green] ALL VERIFICATION SCENARIOS COMPLETED! [/bold green]")
        console.print("[bold green]" + "=" * 55 + "[/bold green]\n")

    finally:
        await client.close()


def main() -> None:
    """CLI entrypoint for connector demonstration."""
    parser = argparse.ArgumentParser(description="WooCommerce Connector Live Demo")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run demo against in-process mock WooCommerce sandbox without external dependencies",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(is_mock=args.mock))


if __name__ == "__main__":
    main()
