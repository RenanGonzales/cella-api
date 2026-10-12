import threading
import uuid
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.domain.stock import needs_restock
from app.models import (
    Category,
    Household,
    Product,
    ProductUnit,
    ShoppingList,
    ShoppingListItem,
    ShoppingListItemStatus,
    ShoppingListStatus,
    StorageArea,
    User,
)
from app.services.shopping_flow import checkout

# --- Helpers --------------------------------------------------------------


def ids_by_name(client, path, headers) -> dict[str, str]:
    return {item["name"]: item["id"] for item in client.get(path, headers=headers).json()}


def new_product(client, headers, name, category, **overrides) -> dict:
    body = {
        "name": name,
        "category_id": ids_by_name(client, "/categories", headers)[category],
        "storage_area_id": ids_by_name(client, "/storage-areas", headers)["Pantry"],
        "unit": "un",
        "consume_step": 1,
        "ideal_quantity": 4,
        "current_quantity": 4,
    }
    body.update(overrides)
    response = client.post("/products", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def add_to_list(client, headers, product, quantity=2):
    client.post(
        "/shopping-list/items",
        json={"product_id": product["id"], "quantity_needed": quantity},
        headers=headers,
    )


def join(client, headers, name) -> dict[str, str]:
    invite = client.get("/me", headers=headers).json()["household"]["invite_code"]
    token = client.post(
        "/auth/register",
        json={
            "name": name,
            "email": f"{name.lower()}@example.com",
            "password": "correct horse battery",
            "invite_code": invite,
        },
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def market_with_layout(client, headers) -> dict:
    market = client.post("/markets", json={"name": "Market"}, headers=headers).json()
    categories = ids_by_name(client, "/categories", headers)
    client.put(
        f"/markets/{market['id']}/layout",
        json={
            "corridors": [
                {"name": "Produce", "category_ids": [categories["Produce"]]},
                {"name": "Bakery", "category_ids": [categories["Bakery"]]},
                {"name": "Dairy", "category_ids": [categories["Dairy"]]},
                {"name": "Cleaning", "category_ids": [categories["Cleaning"]]},
            ]
        },
        headers=headers,
    )
    return market


def items(view) -> list[dict]:
    return [item for group in view["groups"] for item in group["items"]]


def item_named(view, name) -> dict:
    return next(item for item in items(view) if item["name"] == name)


def shopping_setup(client, headers):
    """A list with 2 produce, 1 bakery, 1 dairy and 2 cleaning items, at the market."""
    products = {
        name: new_product(client, headers, name, category)
        for name, category in [
            ("Apples", "Produce"),
            ("Bananas", "Produce"),
            ("Bread", "Bakery"),
            ("Milk", "Dairy"),
            ("Soap", "Cleaning"),
            ("Sponge", "Cleaning"),
        ]
    }
    for product in products.values():
        add_to_list(client, headers, product)
    market = market_with_layout(client, headers)
    response = client.post(
        "/shopping-list/start", json={"market_id": market["id"]}, headers=headers
    )
    assert response.status_code == 200, response.text
    return products, market


# --- Minimum stock (reorder point) ----------------------------------------


def test_reorder_point_rule():
    assert not needs_restock(Decimal(3), Decimal(2), Decimal(6))  # above the minimum
    assert needs_restock(Decimal(2), Decimal(2), Decimal(6))  # reached it
    assert not needs_restock(Decimal(6), Decimal(6), Decimal(6))  # min = ideal, nothing missing


def test_product_waits_for_the_minimum_before_going_on_the_list(client, owner):
    milk = new_product(
        client,
        owner,
        "Milk",
        "Dairy",
        unit="l",
        ideal_quantity=6,
        min_quantity=2,
        current_quantity=6,
    )

    for _ in range(3):  # 6 -> 3: still above the minimum
        body = client.post(f"/products/{milk['id']}/consume", headers=owner).json()
    assert body["added_to_list"] is False
    assert body["product"]["needs_restock"] is False
    assert body["product"]["below_ideal"] is True

    body = client.post(f"/products/{milk['id']}/consume", headers=owner).json()  # 3 -> 2
    assert body["added_to_list"] is True
    view = client.get("/shopping-list", headers=owner).json()
    assert item_named(view, "Milk")["quantity_needed"] == 4.0  # back up to the ideal


def test_minimum_defaults_to_the_ideal(client, owner):
    product = new_product(client, owner, "Rice", "Grains & Pasta", ideal_quantity=5)

    assert product["min_quantity"] == 5.0


def test_minimum_cannot_exceed_the_ideal(client, owner):
    categories = ids_by_name(client, "/categories", owner)
    areas = ids_by_name(client, "/storage-areas", owner)
    body = {
        "name": "Rice",
        "category_id": categories["Grains & Pasta"],
        "storage_area_id": areas["Pantry"],
        "unit": "kg",
        "consume_step": 1,
        "ideal_quantity": 2,
        "min_quantity": 3,
    }
    assert client.post("/products", json=body, headers=owner).status_code == 422

    product = new_product(client, owner, "Beans", "Grains & Pasta", min_quantity=2)
    response = client.patch(f"/products/{product['id']}", json={"ideal_quantity": 1}, headers=owner)
    assert response.status_code == 422  # new ideal would be below the current minimum


def test_needs_restock_filter(client, owner):
    new_product(client, owner, "Low", "Snacks", min_quantity=2, current_quantity=1)
    new_product(client, owner, "Fine", "Snacks", min_quantity=2, current_quantity=3)

    response = client.get("/products", params={"needs_restock": True}, headers=owner)

    assert [product["name"] for product in response.json()] == ["Low"]


def test_undo_above_the_minimum_removes_the_automatic_item(client, owner):
    milk = new_product(
        client, owner, "Milk", "Dairy", ideal_quantity=6, min_quantity=2, current_quantity=3
    )
    event_id = client.post(f"/products/{milk['id']}/consume", headers=owner).json()[
        "consumption_event_id"
    ]  # 3 -> 2: on the list

    client.post(f"/consumption-events/{event_id}/undo", headers=owner)  # back to 3

    assert items(client.get("/shopping-list", headers=owner).json()) == []


# --- Start and cancel -----------------------------------------------------


def test_start_sorts_by_the_chosen_market(client, owner):
    shopping_setup(client, owner)

    view = client.get("/shopping-list", headers=owner).json()

    assert view["status"] == "shopping"
    assert [group["name"] for group in view["groups"]] == [
        "Produce",
        "Bakery",
        "Dairy",
        "Cleaning",
    ]


def test_cannot_start_with_an_empty_list(client, owner):
    market = market_with_layout(client, owner)

    response = client.post("/shopping-list/start", json={"market_id": market["id"]}, headers=owner)

    assert response.status_code == 409


def test_cancel_goes_back_to_open_and_resets_the_cart(client, owner):
    shopping_setup(client, owner)
    bread = item_named(client.get("/shopping-list", headers=owner).json(), "Bread")
    client.patch(f"/shopping-list/items/{bread['id']}", json={"status": "checked"}, headers=owner)

    view = client.post("/shopping-list/cancel", headers=owner).json()

    assert view["status"] == "open"
    assert view["market_id"] is None
    assert all(item["status"] == "pending" for item in items(view))
    assert len(items(view)) == 6  # nothing lost


def test_store_actions_require_shopping(client, owner):
    bread = new_product(client, owner, "Bread", "Bakery")
    add_to_list(client, owner, bread)
    item = items(client.get("/shopping-list", headers=owner).json())[0]

    check = client.patch(
        f"/shopping-list/items/{item['id']}", json={"status": "checked"}, headers=owner
    )
    finish = client.post("/shopping-list/checkout", headers=owner)

    assert check.status_code == finish.status_code == 409


# --- Split ----------------------------------------------------------------


def test_split_gives_each_person_a_block_of_corridors(client, owner):
    shopping_setup(client, owner)
    partner = join(client, owner, "Carol")
    me = client.get("/me", headers=owner).json()
    carol_id = client.get("/me", headers=partner).json()["id"]

    view = client.post(
        "/shopping-list/split", json={"user_ids": [me["id"], carol_id]}, headers=owner
    ).json()

    by_corridor = {
        group["name"]: {item["assigned_user_id"] for item in group["items"]}
        for group in view["groups"]
    }
    # 6 items: Produce (2) + Bakery (1) for the first person, Dairy (1) + Cleaning (2) for Carol.
    assert by_corridor == {
        "Produce": {me["id"]},
        "Bakery": {me["id"]},
        "Dairy": {carol_id},
        "Cleaning": {carol_id},
    }

    mine = client.get("/shopping-list", params={"mine": True}, headers=partner).json()
    assert [group["name"] for group in mine["groups"]] == ["Dairy", "Cleaning"]
    assert mine["item_count"] == 3


def test_split_rejects_people_from_other_households(client, owner, stranger):
    shopping_setup(client, owner)
    stranger_id = client.get("/me", headers=stranger).json()["id"]

    response = client.post("/shopping-list/split", json={"user_ids": [stranger_id]}, headers=owner)

    assert response.status_code == 404


def test_reassign_an_item_by_hand(client, owner):
    shopping_setup(client, owner)
    partner_id = client.get("/me", headers=join(client, owner, "Carol")).json()["id"]
    milk = item_named(client.get("/shopping-list", headers=owner).json(), "Milk")

    view = client.patch(
        f"/shopping-list/items/{milk['id']}", json={"assigned_user_id": partner_id}, headers=owner
    ).json()
    assert item_named(view, "Milk")["assigned_user_id"] == partner_id

    view = client.patch(
        f"/shopping-list/items/{milk['id']}", json={"assigned_user_id": None}, headers=owner
    ).json()
    assert item_named(view, "Milk")["assigned_user_id"] is None


# --- Checking items -------------------------------------------------------


def test_check_defaults_to_the_quantity_needed(client, owner):
    shopping_setup(client, owner)
    bread = item_named(client.get("/shopping-list", headers=owner).json(), "Bread")

    view = client.patch(
        f"/shopping-list/items/{bread['id']}", json={"status": "checked"}, headers=owner
    ).json()
    assert item_named(view, "Bread")["quantity_bought"] == 2.0

    view = client.patch(
        f"/shopping-list/items/{bread['id']}", json={"quantity_bought": 3}, headers=owner
    ).json()
    assert item_named(view, "Bread")["quantity_bought"] == 3.0  # the pack was bigger

    view = client.patch(
        f"/shopping-list/items/{bread['id']}", json={"status": "pending"}, headers=owner
    ).json()
    assert item_named(view, "Bread")["quantity_bought"] is None  # back out of the cart


def test_quantity_bought_needs_a_checked_item(client, owner):
    shopping_setup(client, owner)
    bread = item_named(client.get("/shopping-list", headers=owner).json(), "Bread")

    response = client.patch(
        f"/shopping-list/items/{bread['id']}", json={"quantity_bought": 3}, headers=owner
    )

    assert response.status_code == 422


# --- Checkout -------------------------------------------------------------


def test_checkout_updates_stock_archives_and_carries_over(client, owner):
    products, _ = shopping_setup(client, owner)
    view = client.get("/shopping-list", headers=owner).json()
    for name in ("Apples", "Bread"):
        client.patch(
            f"/shopping-list/items/{item_named(view, name)['id']}",
            json={"status": "checked"},
            headers=owner,
        )
    client.patch(
        f"/shopping-list/items/{item_named(view, 'Milk')['id']}",
        json={"status": "not_found"},
        headers=owner,
    )

    response = client.post("/shopping-list/checkout", headers=owner)

    assert response.status_code == 200
    body = response.json()
    assert body["items_bought"] == 2
    assert body["items_carried_over"] == 4  # Milk (not found) + 3 still pending
    assert body["items_without_price"] == 2
    apples = client.get(f"/products/{products['Apples']['id']}", headers=owner).json()
    assert apples["current_quantity"] == 6.0  # 4 + 2 bought

    next_list = client.get("/shopping-list", headers=owner).json()
    assert next_list["status"] == "open"
    assert {item["name"] for item in items(next_list)} == {"Bananas", "Milk", "Soap", "Sponge"}
    assert all(item["assigned_user_id"] is None for item in items(next_list))

    second = client.post("/shopping-list/checkout", headers=owner)
    assert second.status_code == 409  # nothing in progress anymore


def test_checkout_with_everything_bought_leaves_no_list(client, owner):
    bread = new_product(client, owner, "Bread", "Bakery")
    add_to_list(client, owner, bread)
    market = market_with_layout(client, owner)
    client.post("/shopping-list/start", json={"market_id": market["id"]}, headers=owner)
    item = items(client.get("/shopping-list", headers=owner).json())[0]
    client.patch(f"/shopping-list/items/{item['id']}", json={"status": "checked"}, headers=owner)

    body = client.post("/shopping-list/checkout", headers=owner).json()

    assert body["items_carried_over"] == 0
    assert client.get("/shopping-list", headers=owner).json()["id"] is None


# --- Purchases ------------------------------------------------------------


def checked_out_purchase(client, headers) -> tuple[str, dict]:
    products, _ = shopping_setup(client, headers)
    view = client.get("/shopping-list", headers=headers).json()
    for name, quantity in (("Apples", 2), ("Bread", 1)):
        client.patch(
            f"/shopping-list/items/{item_named(view, name)['id']}",
            json={"status": "checked", "quantity_bought": quantity},
            headers=headers,
        )
    purchase_id = client.post("/shopping-list/checkout", headers=headers).json()["purchase_id"]
    return purchase_id, products


def test_fill_prices_at_home_and_get_totals(client, owner):
    purchase_id, products = checked_out_purchase(client, owner)
    detail = client.get(f"/purchases/{purchase_id}", headers=owner).json()
    apples = next(item for item in detail["items"] if item["name"] == "Apples")
    bread = next(item for item in detail["items"] if item["name"] == "Bread")

    client.patch(
        f"/purchases/{purchase_id}/items/{apples['id']}",
        json={"unit_price_cents": 349},
        headers=owner,
    )
    detail = client.patch(
        f"/purchases/{purchase_id}/items/{bread['id']}",
        json={"unit_price_cents": 899},
        headers=owner,
    ).json()

    assert detail["total_cents"] == 2 * 349 + 899
    assert detail["items_without_price"] == 0
    assert next(i for i in detail["items"] if i["name"] == "Apples")["line_total_cents"] == 698

    product = client.get(f"/products/{products['Apples']['id']}", headers=owner).json()
    assert product["last_price_cents"] == 349  # feeds the next shopping list

    history = client.get("/purchases", headers=owner).json()
    assert history[0]["id"] == purchase_id
    assert history[0]["market_name"] == "Market"


def test_only_bought_items_get_a_price(client, owner):
    purchase_id, _ = checked_out_purchase(client, owner)
    detail = client.get(f"/purchases/{purchase_id}", headers=owner).json()
    pending = next(item for item in detail["items"] if item["status"] != "checked")

    response = client.patch(
        f"/purchases/{purchase_id}/items/{pending['id']}",
        json={"unit_price_cents": 100},
        headers=owner,
    )

    assert response.status_code == 409


def test_other_households_cannot_see_purchases(client, owner, stranger):
    purchase_id, _ = checked_out_purchase(client, owner)

    assert client.get(f"/purchases/{purchase_id}", headers=stranger).status_code == 404
    assert client.get("/purchases", headers=stranger).json() == []


# --- Concurrency ----------------------------------------------------------


def test_two_phones_finishing_at_once_add_stock_only_once():
    """Both phones tap "finish" at the same instant, each with its own connection.

    The list row is locked: one checkout wins, the other gets 409, and the stock is
    added once. Uses committed data, so it cleans up after itself.
    """
    with SessionLocal() as setup:
        household = Household(name="Race", invite_code=f"C{uuid.uuid4().hex[:7].upper()}")
        setup.add(household)
        setup.flush()
        users = [
            User(
                household_id=household.id,
                name=name,
                email=f"{name}-{uuid.uuid4().hex[:8]}@race.test",
                password_hash="x",
            )
            for name in ("ana", "bia")
        ]
        area = StorageArea(household_id=household.id, name="Pantry", position=0)
        category = Category(household_id=household.id, name="Bakery")
        setup.add_all([*users, area, category])
        setup.flush()
        bread = Product(
            household_id=household.id,
            category_id=category.id,
            storage_area_id=area.id,
            name="Bread",
            unit=ProductUnit.UNIT,
            consume_step=Decimal("1"),
            ideal_quantity=Decimal("2"),
            min_quantity=Decimal("1"),
            current_quantity=Decimal("0"),
        )
        setup.add(bread)
        setup.flush()
        shopping = ShoppingList(household_id=household.id, status=ShoppingListStatus.SHOPPING)
        setup.add(shopping)
        setup.flush()
        setup.add(
            ShoppingListItem(
                shopping_list_id=shopping.id,
                product_id=bread.id,
                quantity_needed=Decimal("2"),
                quantity_bought=Decimal("2"),
                status=ShoppingListItemStatus.CHECKED,
            )
        )
        setup.commit()
        household_id, bread_id, user_ids = household.id, bread.id, [u.id for u in users]

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def finish(user_id):
        with SessionLocal() as session:
            user = session.get(User, user_id)
            barrier.wait()
            try:
                checkout(session, user)
                session.commit()
                outcomes.append("ok")
            except Exception as error:  # the loser gets HTTP 409
                session.rollback()
                outcomes.append(getattr(error, "status_code", repr(error)))

    threads = [threading.Thread(target=finish, args=(user_id,)) for user_id in user_ids]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert sorted(outcomes, key=str) == sorted(["ok", 409], key=str)
        with SessionLocal() as check:
            assert check.get(Product, bread_id).current_quantity == Decimal("2")
            archived = check.scalars(
                select(ShoppingList).where(ShoppingList.household_id == household_id)
            ).all()
            assert [lst.status for lst in archived] == [ShoppingListStatus.ARCHIVED]
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(delete(Household).where(Household.id == household_id))
            cleanup.commit()
