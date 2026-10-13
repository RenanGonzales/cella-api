"""The demo household: its data, and the private copy each visitor gets.

The same data backs the local seed (scripts/seed.py, fixed logins for development) and
the public demo, where POST /auth/demo builds a fresh copy per visitor so that nobody
sees anyone else's clicks. Copies expire and are deleted after `demo_ttl_hours`.
"""

import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.defaults import DEFAULT_CATEGORIES, DEFAULT_STORAGE_AREAS
from app.domain.invite import generate_invite_code
from app.domain.stock import needs_restock, quantity_needed
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

DEMO_PEOPLE = ["Alex", "Sam"]
SANDBOX_EMAIL_DOMAIN = "sandbox.cella.app"
INVITE_CODE_ATTEMPTS = 5

STORAGE_AREAS = DEFAULT_STORAGE_AREAS
CATEGORIES = DEFAULT_CATEGORIES

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


def demo_minimum(unit: str, ideal: Decimal) -> Decimal:
    """Demo reorder point: half of the ideal (whole units for countable items)."""
    half = ideal / 2
    return Decimal(int(half)) if unit == "un" else half


def build_demo_household(
    db: Session,
    *,
    invite_code: str,
    people: list[tuple[str, str]],
    password_hash: str,
    expires_at: datetime | None,
) -> tuple[Household, list[User]]:
    """Create the demo household: people, areas, a market with corridors, 35 products,
    last week's purchase (for prices), some consumption history and an open list."""
    rng = random.Random(42)  # deterministic demo data
    now = datetime.now(UTC)

    household = Household(name="Demo House", invite_code=invite_code, demo_expires_at=expires_at)
    db.add(household)
    db.flush()

    users = [
        User(household_id=household.id, name=name, email=email, password_hash=password_hash)
        for name, email in people
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
            min_quantity=demo_minimum(unit, Decimal(ideal)),
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

        if needs_restock(product.current_quantity, product.min_quantity, product.ideal_quantity):
            needed = quantity_needed(Decimal(ideal), Decimal(current), Decimal(step))
            db.add(
                ShoppingListItem(
                    shopping_list_id=open_list.id,
                    product_id=product.id,
                    quantity_needed=needed,
                )
            )

    db.flush()
    return household, users


# --- Per-visitor sandboxes ---------------------------------------------------


def delete_expired_sandboxes(db: Session, now: datetime | None = None) -> int:
    """Delete demo copies past their expiry; foreign keys cascade to everything they own."""
    result = db.execute(
        delete(Household).where(Household.demo_expires_at < (now or datetime.now(UTC)))
    )
    return result.rowcount or 0


def _unique_invite_code(db: Session) -> str:
    for _ in range(INVITE_CODE_ATTEMPTS):
        code = generate_invite_code()
        if db.scalar(select(Household.id).where(Household.invite_code == code)) is None:
            return code
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not create the demo")


def create_sandbox(db: Session, settings: Settings) -> tuple[Household, list[User]]:
    """A private copy of the demo household for one visitor.

    Expired copies are cleaned up first, and the number of live copies is capped so that
    repeated clicks cannot grow the database without limit.
    """
    now = datetime.now(UTC)
    delete_expired_sandboxes(db, now)
    live = db.scalar(select(func.count()).where(Household.demo_expires_at.is_not(None))) or 0
    if live >= settings.demo_max_sandboxes:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The demo is busy. Try again in a few minutes."
        )

    # Sandbox people never log in with a password: a random one, hashed with the minimum
    # bcrypt cost (it is never checked, so there is no reason to spend CPU on it).
    unusable = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt(rounds=4)).decode()
    suffix = uuid.uuid4().hex[:12]
    return build_demo_household(
        db,
        invite_code=_unique_invite_code(db),
        people=[(name, f"{name.lower()}.{suffix}@{SANDBOX_EMAIL_DOMAIN}") for name in DEMO_PEOPLE],
        password_hash=unusable,
        expires_at=now + timedelta(hours=settings.demo_ttl_hours),
    )
