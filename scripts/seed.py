"""Create (or reset) the public demo household.

Run with: python -m scripts.seed

The script is idempotent: it deletes the demo household (and everything that
belongs to it) before recreating it, so it can also be used as the daily reset.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domain.stock import quantity_needed
from app.models import (
    Category,
    ConsumptionEvent,
    Corridor,
    CorridorCategory,
    Household,
    Market,
    Product,
    ProductUnit,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
    StorageArea,
    User,
)

DEMO_INVITE_CODE = "DEMO2026"
DEMO_PASSWORD = "demo1234"

USERS = [("Alex", "alex@demo.cella.app"), ("Sam", "sam@demo.cella.app")]

STORAGE_AREAS = ["Fridge", "Freezer", "Pantry", "Bathroom", "Laundry"]

CATEGORIES = [
    "Produce",
    "Bakery",
    "Dairy",
    "Meat",
    "Frozen",
    "Grains & Pasta",
    "Canned & Sauces",
    "Breakfast",
    "Snacks",
    "Beverages",
    "Cleaning",
    "Personal Care",
    "Paper Goods",
]

# Corridors in walking order and the categories found in each one.
# "Paper Goods" is intentionally left unmapped to show the "Other" group.
CORRIDORS = [
    ("Produce", ["Produce"]),
    ("Bakery", ["Bakery"]),
    ("Grains & Canned", ["Grains & Pasta", "Canned & Sauces"]),
    ("Breakfast & Snacks", ["Breakfast", "Snacks"]),
    ("Beverages", ["Beverages"]),
    ("Cleaning", ["Cleaning"]),
    ("Personal Care", ["Personal Care"]),
    ("Meat", ["Meat"]),
    ("Dairy", ["Dairy"]),
    ("Frozen", ["Frozen"]),
]

# name, brand, category, storage area, unit, consume step, ideal, current, price (cents per unit)
PRODUCTS = [
    ("Whole milk", "Valley Farm", "Dairy", "Fridge", "l", "1", "6", "2", 549),
    ("Butter", "Valley Farm", "Dairy", "Fridge", "un", "1", "1", "0", 1290),
    ("Mozzarella", None, "Dairy", "Fridge", "kg", "0.2", "0.4", "0.1", 5990),
    ("Greek yogurt", "Pure Dairy", "Dairy", "Fridge", "un", "1", "6", "4", 349),
    ("Eggs", None, "Dairy", "Fridge", "un", "1", "12", "5", 89),
    ("Bananas", None, "Produce", "Pantry", "kg", "1", "2", "1.2", 699),
    ("Tomatoes", None, "Produce", "Fridge", "kg", "0.5", "1", "0.5", 899),
    ("Onions", None, "Produce", "Pantry", "kg", "1", "2", "1.5", 549),
    ("Potatoes", None, "Produce", "Pantry", "kg", "1", "3", "3", 499),
    ("Lettuce", None, "Produce", "Fridge", "un", "1", "1", "0", 399),
    ("Bread loaf", "Golden Oven", "Bakery", "Pantry", "un", "1", "2", "1", 899),
    ("Chicken breast", None, "Meat", "Freezer", "kg", "1", "2", "2", 2290),
    ("Ground beef", None, "Meat", "Freezer", "kg", "0.5", "1", "0.5", 3990),
    ("Frozen peas", "Green Field", "Frozen", "Freezer", "un", "1", "1", "1", 790),
    ("Ice cream", "Polar", "Frozen", "Freezer", "un", "1", "1", "1", 2490),
    ("Rice", "Grain Co.", "Grains & Pasta", "Pantry", "kg", "5", "6", "3", 549),
    ("Black beans", "Grain Co.", "Grains & Pasta", "Pantry", "kg", "1", "2", "2", 899),
    ("Pasta", "Nonna", "Grains & Pasta", "Pantry", "kg", "0.5", "1", "1", 1180),
    ("Flour", None, "Grains & Pasta", "Pantry", "kg", "1", "1", "1", 599),
    ("Sugar", None, "Grains & Pasta", "Pantry", "kg", "1", "1", "0.5", 479),
    ("Tomato sauce", "Nonna", "Canned & Sauces", "Pantry", "un", "1", "3", "3", 389),
    ("Olive oil", "Olea", "Canned & Sauces", "Pantry", "l", "0.5", "0.5", "0.5", 5980),
    ("Coffee", "Morning Roast", "Breakfast", "Pantry", "kg", "0.5", "1", "0.5", 5990),
    ("Oats", None, "Breakfast", "Pantry", "kg", "0.5", "0.5", "0.5", 1580),
    ("Crackers", None, "Snacks", "Pantry", "un", "1", "2", "2", 459),
    ("Orange juice", "Citrus", "Beverages", "Fridge", "l", "1", "2", "1", 1190),
    ("Sparkling water", None, "Beverages", "Pantry", "un", "1", "6", "6", 299),
    ("Dish soap", "Sparkle", "Cleaning", "Laundry", "un", "1", "2", "1", 279),
    ("Laundry detergent", "Sparkle", "Cleaning", "Laundry", "l", "3", "3", "3", 1330),
    ("Fabric softener", "Sparkle", "Cleaning", "Laundry", "l", "2", "2", "2", 899),
    ("Toothpaste", "Bright", "Personal Care", "Bathroom", "un", "1", "2", "2", 699),
    ("Shampoo", "Bright", "Personal Care", "Bathroom", "un", "1", "1", "1", 1890),
    ("Soap bar", None, "Personal Care", "Bathroom", "un", "1", "4", "2", 249),
    ("Toilet paper", "Soft", "Paper Goods", "Bathroom", "un", "1", "12", "4", 199),
    ("Paper towels", "Soft", "Paper Goods", "Laundry", "un", "1", "2", "2", 599),
]


def reset_demo(db: Session) -> None:
    """Delete the demo household; foreign keys cascade to everything it owns."""
    db.execute(delete(Household).where(Household.invite_code == DEMO_INVITE_CODE))
    db.flush()


def create_demo(db: Session) -> Household:
    rng = random.Random(42)  # deterministic demo data
    now = datetime.now(UTC)

    household = Household(name="Demo House", invite_code=DEMO_INVITE_CODE)
    db.add(household)
    db.flush()

    password_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    users = [
        User(household_id=household.id, name=name, email=email, password_hash=password_hash)
        for name, email in USERS
    ]
    areas = {
        name: StorageArea(household_id=household.id, name=name, position=index)
        for index, name in enumerate(STORAGE_AREAS)
    }
    categories = {name: Category(household_id=household.id, name=name) for name in CATEGORIES}
    db.add_all([*users, *areas.values(), *categories.values()])

    market = Market(household_id=household.id, name="Neighborhood Market")
    db.add(market)
    db.flush()

    for position, (corridor_name, category_names) in enumerate(CORRIDORS):
        corridor = Corridor(market_id=market.id, name=corridor_name, position=position)
        db.add(corridor)
        db.flush()
        for category_name in category_names:
            db.add(
                CorridorCategory(
                    market_id=market.id,
                    corridor_id=corridor.id,
                    category_id=categories[category_name].id,
                )
            )

    # Last week's purchase: archived list that provides each product's "last price".
    last_purchase = ShoppingList(
        household_id=household.id,
        market_id=market.id,
        status=ShoppingListStatus.ARCHIVED,
        started_at=now - timedelta(days=7, hours=1),
        completed_at=now - timedelta(days=7),
    )
    # Current list: products below their ideal stock.
    open_list = ShoppingList(household_id=household.id, status=ShoppingListStatus.OPEN)
    db.add_all([last_purchase, open_list])
    db.flush()

    for name, brand, category, area, unit, step, ideal, current, price in PRODUCTS:
        product = Product(
            household_id=household.id,
            category_id=categories[category].id,
            storage_area_id=areas[area].id,
            name=name,
            brand=brand,
            unit=ProductUnit(unit),
            consume_step=Decimal(step),
            ideal_quantity=Decimal(ideal),
            current_quantity=Decimal(current),
        )
        db.add(product)
        db.flush()

        db.add(
            ShoppingListItem(
                shopping_list_id=last_purchase.id,
                product_id=product.id,
                quantity_needed=Decimal(step),
                quantity_bought=Decimal(step),
                unit_price_cents=price,
                status=ShoppingListItemStatus.CHECKED,
            )
        )

        # A few consumption events over the last two weeks, for autonomy forecasts.
        for _ in range(rng.randint(0, 4)):
            db.add(
                ConsumptionEvent(
                    product_id=product.id,
                    user_id=rng.choice(users).id,
                    quantity=Decimal(step),
                    consumed_at=now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 23)),
                )
            )

        needed = quantity_needed(Decimal(ideal), Decimal(current), Decimal(step))
        if needed > 0:
            db.add(
                ShoppingListItem(
                    shopping_list_id=open_list.id,
                    product_id=product.id,
                    quantity_needed=needed,
                )
            )

    return household


def main() -> None:
    with SessionLocal() as db, db.begin():
        reset_demo(db)
        household = create_demo(db)
        print(
            f"Demo household ready: {household.name} "
            f"({len(PRODUCTS)} products, login {USERS[0][1]} / {DEMO_PASSWORD})"
        )


if __name__ == "__main__":
    main()
