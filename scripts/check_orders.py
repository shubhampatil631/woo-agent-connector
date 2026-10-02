"""Quick check script to query and print orders using connector tools."""

import asyncio
import sys

from woo_connector.client import WooClient
from woo_connector.config import settings
from woo_connector.tools import list_orders


async def main():
    print(f"Connecting to {settings.base_url}...")
    async with WooClient() as client:
        try:
            page = await list_orders(client, page=1, per_page=5)
            print(f"Total Orders: {page.total or 'N/A'} (Showing {len(page.items)})")
            for order in page.items:
                print(
                    f" - Order #{order.number} | Status: {order.status:<10} | "
                    f"Total: {order.currency} {order.total} | Customer: {order.customer_ref}"
                )
        except Exception as e:
            print(f"Error querying orders: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
