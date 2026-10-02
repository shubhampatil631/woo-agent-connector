"""Database seeding script for local WooCommerce sandbox.

Generates:
- ~40 fictional products (simple, variable, out-of-stock, low-stock, manage_stock disabled)
- ~120 fictional orders across all statuses (pending, processing, on-hold, completed,
  cancelled, refunded, failed)
- Realistic fake customer details using Faker (emails strictly under @example.com)
"""

import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from faker import Faker

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
    # Electronics
    ("Wireless Noise-Canceling Headphones", "Electronics", "99.99", True, 25),
    ("Mechanical RGB Keyboard", "Electronics", "79.50", True, 3),  # low stock
    ("Ultra-HD 4K Action Camera", "Electronics", "149.00", True, 0),  # out of stock
    ("Portable Power Bank 20000mAh", "Electronics", "39.99", True, 45),
    ("Smart LED Desk Lamp", "Electronics", "29.99", False, None),  # manage_stock off
    ("Bluetooth Ergonomic Mouse", "Electronics", "24.99", True, 2),  # low stock
    ("USB-C Multi-Port Hub", "Electronics", "34.50", True, 18),
    ("Wireless Charging Pad", "Electronics", "19.99", True, 0),  # out of stock
    # Apparel (Simple)
    ("Vintage Denim Jacket", "Apparel", "89.00", True, 12),
    ("Waterproof Rain Poncho", "Apparel", "22.50", True, 1),  # low stock
    ("Thermal Winter Beanie", "Apparel", "14.99", True, 60),
    ("Heavyweight Canvas Tote Bag", "Apparel", "18.00", False, None),  # manage_stock off
    ("Polarized UV400 Sunglasses", "Apparel", "35.00", True, 0),  # out of stock
    ("Classic Leather Belt", "Apparel", "28.00", True, 15),
    # Home & Kitchen
    ("Stainless Steel French Press", "Home & Kitchen", "32.00", True, 20),
    ("Ceramic Pour-Over Coffee Dripper", "Home & Kitchen", "18.50", True, 3),  # low stock
    ("Electric Gooseneck Kettle", "Home & Kitchen", "55.00", True, 8),
    ("Bamboo Cutting Board Set", "Home & Kitchen", "25.00", False, None),  # manage_stock off
    ("Insulated Stainless Tumbler 20oz", "Home & Kitchen", "21.99", True, 30),
    ("Non-Stick Cast Iron Skillet 10in", "Home & Kitchen", "42.00", True, 0),  # out of stock
    # Books & Media
    ("Building Resilient Distributed Systems", "Books & Media", "49.99", False, None),
    ("The Pragmatic AI Engineer Handbook", "Books & Media", "44.99", True, 50),
    ("Designing Data-Intensive Applications", "Books & Media", "52.00", True, 2),  # low stock
    ("Digital Art E-Book Bundle", "Books & Media", "15.00", False, None),
    ("Site Reliability Engineering in Practice", "Books & Media", "47.50", True, 14),
    # Sports & Fitness
    ("High-Density Yoga Mat with Strap", "Sports & Fitness", "28.00", True, 15),
    ("Adjustable Dumbbell Set 50lbs", "Sports & Fitness", "189.00", True, 0),  # out of stock
    ("Resistance Loop Exercise Bands", "Sports & Fitness", "12.99", True, 80),
    ("Insulated Sports Hydration Flask", "Sports & Fitness", "24.00", True, 2),  # low stock
    ("Speed Jump Rope with Ball Bearings", "Sports & Fitness", "11.50", False, None),
]

VARIABLE_PRODUCT_TEMPLATES = [
    (
        "Signature Cotton Crewneck T-Shirt",
        "Apparel",
        "24.99",
        [
            {"size": "S", "color": "Black", "price": "24.99", "stock": 10},
            {"size": "M", "color": "Black", "price": "24.99", "stock": 2},  # low
            {"size": "L", "color": "Black", "price": "24.99", "stock": 0},  # out of stock
            {"size": "S", "color": "White", "price": "24.99", "stock": 15},
            {"size": "M", "color": "White", "price": "24.99", "stock": 0},  # out of stock
            {"size": "L", "color": "White", "price": "24.99", "stock": 20},
        ],
    ),
    (
        "Premium Fleece Pullover Hoodie",
        "Apparel",
        "54.00",
        [
            {"size": "M", "color": "Heather Grey", "price": "54.00", "stock": 8},
            {"size": "L", "color": "Heather Grey", "price": "54.00", "stock": 1},  # low
            {"size": "XL", "color": "Heather Grey", "price": "58.00", "stock": 5},
            {"size": "M", "color": "Navy Blue", "price": "54.00", "stock": 0},
            {"size": "L", "color": "Navy Blue", "price": "54.00", "stock": 12},
        ],
    ),
    (
        "All-Weather Trail Running Shoes",
        "Sports & Fitness",
        "119.00",
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
        "129.99",
        [
            {"size": "Standard", "color": "Silver", "price": "129.99", "stock": 14},
            {"size": "Standard", "color": "Matte Black", "price": "139.99", "stock": 2},
            {"size": "Pro Sensor Pack", "color": "Matte Black", "price": "179.99", "stock": 0},
        ],
    ),
    (
        "Modular Ergonomic Desk Chair",
        "Home & Kitchen",
        "249.00",
        [
            {"size": "Standard", "color": "Graphite", "price": "249.00", "stock": 6},
            {"size": "Standard", "color": "Carbon Blue", "price": "249.00", "stock": 0},
            {"size": "Headrest Edition", "color": "Graphite", "price": "299.00", "stock": 3},
        ],
    ),
]


async def main():
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        print("ERROR: WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET must be set in the environment")
        print("Please copy your credentials from the Docker startup logs.")
        sys.exit(1)

    auth = httpx.BasicAuth(CONSUMER_KEY, CONSUMER_SECRET)
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(
        base_url=STORE_URL, auth=auth, headers=headers, timeout=30.0
    ) as client:
        print(f"==> Verifying connection to WooCommerce REST API at {STORE_URL}...")
        try:
            res = await client.get("/wp-json/wc/v3/system_status")
            if res.status_code not in (200, 201):
                print(f"Failed to connect (HTTP {res.status_code}): {res.text[:200]}")
                sys.exit(1)
        except Exception as e:
            print(f"Connection error: {e}")
            sys.exit(1)

        print("==> Connected successfully!")

        # 1. Create Categories
        print("==> Creating categories...")
        cat_map = {}
        for cat in CATEGORIES:
            res = await client.post("/wp-json/wc/v3/products/categories", json=cat)
            if res.status_code in (200, 201):
                cat_data = res.json()
                cat_map[cat["name"]] = cat_data["id"]
            elif res.status_code == 400 and "term_exists" in res.text:
                # Category already exists, fetch it
                existing_res = await client.get(
                    "/wp-json/wc/v3/products/categories", params={"search": cat["name"]}
                )
                if existing_res.status_code == 200 and existing_res.json():
                    cat_map[cat["name"]] = existing_res.json()[0]["id"]
            else:
                print(f"Warning: Category creation failed for {cat['name']}: {res.status_code}")

        # 2. Create Simple Products
        created_products: list[dict[str, Any]] = []
        print(f"==> Creating {len(PRODUCT_TEMPLATES)} simple products...")
        for name, cat_name, price, manage_stock, stock_qty in PRODUCT_TEMPLATES:
            payload: dict[str, Any] = {
                "name": name,
                "type": "simple",
                "regular_price": price,
                "manage_stock": manage_stock,
                "categories": [{"id": cat_map[cat_name]}] if cat_name in cat_map else [],
            }
            if manage_stock and stock_qty is not None:
                payload["stock_quantity"] = stock_qty
                payload["stock_status"] = "instock" if stock_qty > 0 else "outofstock"
            else:
                payload["stock_status"] = "instock"

            res = await client.post("/wp-json/wc/v3/products", json=payload)
            if res.status_code in (200, 201):
                pdata = res.json()
                created_products.append(
                    {"id": pdata["id"], "name": pdata["name"], "price": float(price)}
                )
            else:
                print(f"Failed to create product {name}: {res.status_code} {res.text[:100]}")

        # 3. Create Variable Products with Variations
        print(f"==> Creating {len(VARIABLE_PRODUCT_TEMPLATES)} variable products & variations...")
        for name, cat_name, _base_price, variations in VARIABLE_PRODUCT_TEMPLATES:
            # Create parent variable product
            parent_payload = {
                "name": name,
                "type": "variable",
                "categories": [{"id": cat_map[cat_name]}] if cat_name in cat_map else [],
                "attributes": [
                    {
                        "name": "Size",
                        "variation": True,
                        "options": list(set(v["size"] for v in variations)),
                    },
                    {
                        "name": "Color",
                        "variation": True,
                        "options": list(set(v["color"] for v in variations)),
                    },
                ],
            }
            res = await client.post("/wp-json/wc/v3/products", json=parent_payload)
            if res.status_code not in (200, 201):
                print(f"Failed to create parent variable product {name}: {res.status_code}")
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
                    vdata = var_res.json()
                    created_products.append(
                        {
                            "id": parent_id,
                            "variation_id": vdata["id"],
                            "name": f"{name} - {v['color']}, {v['size']}",
                            "price": float(v["price"]),
                        }
                    )

        print(f"==> Total product catalog created: {len(created_products)} selectable items.")

        if not created_products:
            print("ERROR: No products were created. Cannot create orders.")
            sys.exit(1)

        # 4. Create ~120 Fictional Orders across all statuses
        target_orders = 120
        print(f"==> Generating {target_orders} orders with realistic fake customer data...")

        for i in range(1, target_orders + 1):
            status = ORDER_STATUSES[(i - 1) % len(ORDER_STATUSES)]
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"
            phone = f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
            address_1 = fake.street_address()
            city = fake.city()
            state = fake.state_abbr()
            postcode = fake.postcode()
            country = "US"

            # 1 to 4 random line items per order
            num_items = random.randint(1, 4)
            chosen_items = random.sample(created_products, min(num_items, len(created_products)))
            line_items = []
            for item in chosen_items:
                qty = random.randint(1, 3)
                line_item = {
                    "product_id": item["id"],
                    "quantity": qty,
                }
                if "variation_id" in item:
                    line_item["variation_id"] = item["variation_id"]
                line_items.append(line_item)

            # Distribute dates across last 90 days
            days_ago = random.randint(0, 90)
            order_date = (
                datetime.now(UTC)
                - timedelta(days=days_ago, minutes=random.randint(0, 1440))
            ).isoformat()

            order_payload = {
                "status": status,
                "date_created": order_date,
                "billing": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "company": fake.company() if random.random() > 0.7 else "",
                    "address_1": address_1,
                    "address_2": fake.secondary_address() if random.random() > 0.5 else "",
                    "city": city,
                    "state": state,
                    "postcode": postcode,
                    "country": country,
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
                    "country": country,
                },
                "line_items": line_items,
                "payment_method": random.choice(["bacs", "cheque", "cod", "stripe"]),
                "payment_method_title": random.choice(
                    ["Direct Bank Transfer", "Check payments", "Cash on delivery", "Credit Card"]
                ),
            }

            res = await client.post("/wp-json/wc/v3/orders", json=order_payload)
            if res.status_code in (200, 201):
                if i % 20 == 0 or i == target_orders:
                    print(f"    [{i}/{target_orders}] Orders created (latest status: {status})")
            else:
                print(f"Failed to create order {i}: {res.status_code} {res.text[:100]}")

        total_parents = len(PRODUCT_TEMPLATES) + len(VARIABLE_PRODUCT_TEMPLATES)
        print("\n=======================================================")
        print("  SEEDING COMPLETE!                                    ")
        print(f"  - Products: ~{total_parents} parent items")
        print("  - Variations & Stock Scenarios configured")
        print(f"  - Orders: {target_orders} orders across 7 distinct statuses")
        print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
