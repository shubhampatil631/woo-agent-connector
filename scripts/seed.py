"""Database seeding script for local WooCommerce sandbox.

Generates:
- ~40 fictional products (simple, variable, out-of-stock, low-stock, manage_stock disabled)
- ~120 fictional orders across all statuses (pending, processing, on-hold, completed,
  cancelled, refunded, failed)
- Realistic fake customer details using Faker (emails strictly under @example.com)
"""

import asyncio
import logging
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

fake = Faker()
Faker.seed(42)
random.seed(42)

STORE_URL = os.getenv("WOO_STORE_URL", "http://localhost:8080").rstrip("/")
CONSUMER_KEY = os.getenv("WOO_CONSUMER_KEY", "")
CONSUMER_SECRET = os.getenv("WOO_CONSUMER_SECRET", "")

CATEGORIES = [
    {"name": "Electronics"},
    {"name": "Apparel"},
    {"name": "Home & Kitchen"},
    {"name": "Books & Media"},
    {"name": "Sports & Fitness"},
]

ORDER_STATUSES = [
    "pending",
    "processing",
    "on-hold",
    "completed",
    "cancelled",
    "refunded",
    "failed",
]

PRODUCT_TEMPLATES = [
    ("Wireless Noise-Canceling Headphones", "Electronics", "99.99", True, 25),
    ("Mechanical RGB Keyboard", "Electronics", "79.50", True, 3),
    ("Ultra-HD 4K Action Camera", "Electronics", "149.00", True, 0),
    ("Portable Power Bank 20000mAh", "Electronics", "39.99", True, 45),
    ("Smart LED Desk Lamp", "Electronics", "29.99", False, None),
    ("Bluetooth Ergonomic Mouse", "Electronics", "24.99", True, 2),
    ("USB-C Multi-Port Hub", "Electronics", "34.50", True, 18),
    ("Wireless Charging Pad", "Electronics", "19.99", True, 0),
    ("Vintage Denim Jacket", "Apparel", "89.00", True, 12),
    ("Waterproof Rain Poncho", "Apparel", "22.50", True, 1),
    ("Thermal Winter Beanie", "Apparel", "14.99", True, 60),
    ("Heavyweight Canvas Tote Bag", "Apparel", "18.00", False, None),
    ("Polarized UV400 Sunglasses", "Apparel", "35.00", True, 0),
    ("Classic Leather Belt", "Apparel", "28.00", True, 15),
    ("Stainless Steel French Press", "Home & Kitchen", "32.00", True, 20),
    ("Ceramic Pour-Over Coffee Dripper", "Home & Kitchen", "18.50", True, 3),
    ("Electric Gooseneck Kettle", "Home & Kitchen", "55.00", True, 8),
    ("Bamboo Cutting Board Set", "Home & Kitchen", "25.00", False, None),
    ("Insulated Stainless Tumbler 20oz", "Home & Kitchen", "21.99", True, 30),
    ("Non-Stick Cast Iron Skillet 10in", "Home & Kitchen", "42.00", True, 0),
    ("Building Resilient Distributed Systems", "Books & Media", "49.99", False, None),
    ("The Pragmatic AI Engineer Handbook", "Books & Media", "44.99", True, 50),
    ("Designing Data-Intensive Applications", "Books & Media", "52.00", True, 2),
    ("Digital Art E-Book Bundle", "Books & Media", "15.00", False, None),
    ("Site Reliability Engineering in Practice", "Books & Media", "47.50", True, 14),
    ("High-Density Yoga Mat with Strap", "Sports & Fitness", "28.00", True, 15),
    ("Adjustable Dumbbell Set 50lbs", "Sports & Fitness", "189.00", True, 0),
    ("Resistance Loop Exercise Bands", "Sports & Fitness", "12.99", True, 80),
    ("Insulated Sports Hydration Flask", "Sports & Fitness", "24.00", True, 2),
    ("Speed Jump Rope with Ball Bearings", "Sports & Fitness", "11.50", False, None),
]

VARIABLE_PRODUCT_TEMPLATES = [
    (
        "Signature Cotton Crewneck T-Shirt",
        "Apparel",
        [
            {"size": "S", "color": "Black", "price": "24.99", "stock": 10},
            {"size": "M", "color": "Black", "price": "24.99", "stock": 2},
            {"size": "L", "color": "Black", "price": "24.99", "stock": 0},
            {"size": "S", "color": "White", "price": "24.99", "stock": 15},
            {"size": "M", "color": "White", "price": "24.99", "stock": 0},
            {"size": "L", "color": "White", "price": "24.99", "stock": 20},
        ],
    ),
    (
        "Premium Fleece Pullover Hoodie",
        "Apparel",
        [
            {"size": "M", "color": "Heather Grey", "price": "54.00", "stock": 8},
            {"size": "L", "color": "Heather Grey", "price": "54.00", "stock": 1},
            {"size": "XL", "color": "Heather Grey", "price": "58.00", "stock": 5},
            {"size": "M", "color": "Navy Blue", "price": "54.00", "stock": 0},
            {"size": "L", "color": "Navy Blue", "price": "54.00", "stock": 12},
        ],
    ),
    (
        "All-Weather Trail Running Shoes",
        "Sports & Fitness",
        [
            {"size": "US 8", "color": "Charcoal/Lime", "price": "119.00", "stock": 5},
            {"size": "US 9", "color": "Charcoal/Lime", "price": "119.00", "stock": 0},
            {"size": "US 10", "color": "Charcoal/Lime", "price": "119.00", "stock": 3},
            {"size": "US 11", "color": "Charcoal/Lime", "price": "119.00", "stock": 7},
        ],
    ),
    (
        "Customizable Smart Home Thermostat",
        "Electronics",
        [
            {"size": "Standard", "color": "Silver", "price": "129.99", "stock": 14},
            {"size": "Standard", "color": "Matte Black", "price": "139.99", "stock": 2},
            {"size": "Pro Sensor Pack", "color": "Matte Black", "price": "179.99", "stock": 0},
        ],
    ),
    (
        "Modular Ergonomic Desk Chair",
        "Home & Kitchen",
        [
            {"size": "Standard", "color": "Graphite", "price": "249.00", "stock": 6},
            {"size": "Standard", "color": "Carbon Blue", "price": "249.00", "stock": 0},
            {"size": "Headrest Edition", "color": "Graphite", "price": "299.00", "stock": 3},
        ],
    ),
]


async def seed_categories(client: httpx.AsyncClient) -> dict[str, int]:
    cat_map: dict[str, int] = {}
    for cat in CATEGORIES:
        res = await client.post("/wp-json/wc/v3/products/categories", json=cat)
        if res.status_code in (200, 201):
            cat_map[cat["name"]] = res.json()["id"]
        elif res.status_code == 400:
            existing = await client.get(
                "/wp-json/wc/v3/products/categories", params={"search": cat["name"]}
            )
            if existing.status_code == 200 and existing.json():
                cat_map[cat["name"]] = existing.json()[0]["id"]
    return cat_map


async def seed_products(
    client: httpx.AsyncClient, cat_map: dict[str, int]
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for name, cat_name, price, manage_stock, stock_qty in PRODUCT_TEMPLATES:
        payload: dict[str, Any] = {
            "name": name,
            "type": "simple",
            "regular_price": price,
            "manage_stock": manage_stock,
            "categories": [{"id": cat_map[cat_name]}] if cat_name in cat_map else [],
            "stock_status": (
                "instock" if (not manage_stock or (stock_qty or 0) > 0) else "outofstock"
            ),
        }
        if manage_stock and stock_qty is not None:
            payload["stock_quantity"] = stock_qty

        res = await client.post("/wp-json/wc/v3/products", json=payload)
        if res.status_code in (200, 201):
            catalog.append({"id": res.json()["id"], "name": name, "price": float(price)})

    for name, cat_name, variations in VARIABLE_PRODUCT_TEMPLATES:
        parent_payload = {
            "name": name,
            "type": "variable",
            "categories": [{"id": cat_map[cat_name]}] if cat_name in cat_map else [],
            "attributes": [
                {
                    "name": "Size",
                    "variation": True,
                    "options": list({v["size"] for v in variations}),
                },
                {
                    "name": "Color",
                    "variation": True,
                    "options": list({v["color"] for v in variations}),
                },
            ],
        }
        res = await client.post("/wp-json/wc/v3/products", json=parent_payload)
        if res.status_code not in (200, 201):
            continue

        parent_id = res.json()["id"]
        for v in variations:
            var_payload = {
                "regular_price": v["price"],
                "manage_stock": True,
                "stock_quantity": v["stock"],
                "stock_status": "instock" if v["stock"] > 0 else "outofstock",
                "attributes": [
                    {"name": "Size", "option": v["size"]},
                    {"name": "Color", "option": v["color"]},
                ],
            }
            var_res = await client.post(
                f"/wp-json/wc/v3/products/{parent_id}/variations", json=var_payload
            )
            if var_res.status_code in (200, 201):
                catalog.append(
                    {
                        "id": parent_id,
                        "variation_id": var_res.json()["id"],
                        "name": f"{name} ({v['color']}, {v['size']})",
                        "price": float(v["price"]),
                    }
                )

    return catalog


async def seed_orders(
    client: httpx.AsyncClient, catalog: list[dict[str, Any]], count: int = 120
) -> int:
    created = 0
    for i in range(1, count + 1):
        status = ORDER_STATUSES[(i - 1) % len(ORDER_STATUSES)]
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"
        phone = f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
        address_1 = fake.street_address()
        city = fake.city()
        state = fake.state_abbr()
        postcode = fake.postcode()

        chosen_items = random.sample(catalog, min(random.randint(1, 4), len(catalog)))
        line_items = [
            {
                "product_id": item["id"],
                "quantity": random.randint(1, 3),
                **({"variation_id": item["variation_id"]} if "variation_id" in item else {}),
            }
            for item in chosen_items
        ]

        days_ago = random.randint(0, 90)
        order_date = (
            datetime.now(UTC) - timedelta(days=days_ago, minutes=random.randint(0, 1440))
        ).isoformat()

        payload = {
            "status": status,
            "date_created": order_date,
            "billing": {
                "first_name": first_name,
                "last_name": last_name,
                "company": fake.company() if random.random() > 0.7 else "",
                "address_1": address_1,
                "city": city,
                "state": state,
                "postcode": postcode,
                "country": "US",
                "email": email,
                "phone": phone,
            },
            "shipping": {
                "first_name": first_name,
                "last_name": last_name,
                "address_1": address_1,
                "city": city,
                "state": state,
                "postcode": postcode,
                "country": "US",
            },
            "line_items": line_items,
            "payment_method": random.choice(["bacs", "cod", "stripe"]),
            "payment_method_title": "Online / Card Payment",
        }

        res = await client.post("/wp-json/wc/v3/orders", json=payload)
        if res.status_code in (200, 201):
            created += 1
            if created % 25 == 0 or created == count:
                logger.info("Created %d/%d orders (latest status: %s)", created, count, status)
        else:
            logger.warning("Order creation failed for index %d: %s", i, res.status_code)

    return created


async def main():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        logger.error("WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET must be configured.")
        sys.exit(1)

    auth = httpx.BasicAuth(CONSUMER_KEY, CONSUMER_SECRET)
    async with httpx.AsyncClient(
        base_url=STORE_URL, auth=auth, timeout=30.0, headers={"Content-Type": "application/json"}
    ) as client:
        logger.info("Connecting to WooCommerce at %s...", STORE_URL)
        res = await client.get("/wp-json/wc/v3/system_status")
        if res.status_code not in (200, 201):
            logger.error("Authentication check failed with HTTP %d", res.status_code)
            sys.exit(1)

        logger.info("Seeding categories and products...")
        cat_map = await seed_categories(client)
        catalog = await seed_products(client, cat_map)
        logger.info("Catalog created: %d items available for orders.", len(catalog))

        if not catalog:
            logger.error("No products available to generate orders.")
            sys.exit(1)

        logger.info("Seeding 120 orders...")
        total_orders = await seed_orders(client, catalog, count=120)
        logger.info(
            "Seeding completed: %d products/variations, %d orders.",
            len(catalog),
            total_orders,
        )


if __name__ == "__main__":
    asyncio.run(main())
