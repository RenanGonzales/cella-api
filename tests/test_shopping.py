import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import (
    Category,
    ConsumptionEvent,
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
from app.services.shopping import consume_product
from scripts.seed import create_demo, reset_demo


def ids_by_name(client, path, headers) -> dict[str, str]:
    return {item["name"]: item["id"] for item in client.get(path, headers=headers).json()}


def new_product(client, headers, **overrides) -> dict:
    areas = ids_by_name(client, "/storage-areas", headers)
    categories = ids_by_name(client, "/categories", headers)
    body = {
        "name": "Rice",
        "category_id": categories["Grains & Pasta"],
        "storage_area_id": areas["Pantry"],
        "unit": "kg",
        "consume_step": 5,  # 5 kg bag
        "ideal_quantity": 6,
        "current_quantity": 10,
    }
    body.update(overrides)
    return client.post("/products", json=body, headers=headers).json()


def consume(client, headers, product_id, **body):
    return client.post(f"/products/{product_id}/consume", json=body or None, headers=headers)


def list_items(client, headers, **params) -> list[dict]:
    view = client.get("/shopping-list", params=params, headers=headers).json()
    return [item for group in view["groups"] for item in group["items"]]


def demo_headers(client, db) -> dict[str, str]:
    reset_demo(db)
    create_demo(db)
    db.flush()
    return {"Authorization": f"Bearer {client.post('/auth/demo').json()['access_token']}"}


# --- Consume --------------------------------------------------------------


def test_consume_removes_one_step_and_records_the_event(client, owner, db):
    rice = new_product(client, owner)

    response = consume(client, owner, rice["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["product"]["current_quantity"] == 5.0
    assert body["consumed"] == 5.0
    assert body["added_to_list"] is True  # 5 < 6
    event = db.get(ConsumptionEvent, uuid.UUID(body["consumption_event_id"]))
    assert event.quantity == Decimal("5")


def test_consume_puts_whole_packages_on_the_list(client, owner):
    rice = new_product(client, owner)

    consume(client, owner, rice["id"])  # 10 -> 5 kg, ideal 6

    [item] = list_items(client, owner)
    assert item["name"] == "Rice"
    assert item["quantity_needed"] == 5.0  # 1 kg missing, rounded up to one 5 kg bag
    assert item["added_manually"] is False


def test_consume_a_custom_quantity(client, owner):
    eggs = new_product(
        client,
        owner,
        name="Eggs",
        unit="un",
        consume_step=1,
        ideal_quantity=12,
        current_quantity=12,
    )

    body = consume(client, owner, eggs["id"], quantity=3).json()

    assert body["product"]["current_quantity"] == 9.0
    assert body["consumed"] == 3.0


def test_stock_never_goes_below_zero(client, owner):
    milk = new_product(client, owner, name="Milk", unit="l", consume_step=1, current_quantity=0.5)

    first = consume(client, owner, milk["id"]).json()
    second = consume(client, owner, milk["id"]).json()

    assert first["consumed"] == 0.5  # only what was really there
    assert first["product"]["current_quantity"] == 0.0
    assert second["consumed"] == 0.0
    assert second["consumption_event_id"] is None  # nothing removed, nothing recorded


def test_archived_products_cannot_be_consumed(client, owner):
    rice = new_product(client, owner)
    client.post(f"/products/{rice['id']}/archive", headers=owner)

    assert consume(client, owner, rice["id"]).status_code == 409


def test_cannot_consume_another_households_product(client, owner, stranger):
    rice = new_product(client, owner)

    assert consume(client, stranger, rice["id"]).status_code == 404
    assert client.get(f"/products/{rice['id']}", headers=owner).json()["current_quantity"] == 10.0


def test_consume_keeps_a_quantity_chosen_by_hand(client, owner):
    rice = new_product(client, owner, current_quantity=5)
    client.post(
        "/shopping-list/items",
        json={"product_id": rice["id"], "quantity_needed": 20},
        headers=owner,
    )

    consume(client, owner, rice["id"])  # automatic need would be 5 kg

    [item] = list_items(client, owner)
    assert item["quantity_needed"] == 20.0


def test_consume_during_shopping_adds_a_pending_item(client, owner, db):
    rice = new_product(client, owner)
    beans = new_product(client, owner, name="Beans", consume_step=1, ideal_quantity=2)
    consume(client, owner, rice["id"])
    household_id = db.get(Product, uuid.UUID(rice["id"])).household_id
    active = db.scalar(select(ShoppingList).where(ShoppingList.household_id == household_id))
    active.status = ShoppingListStatus.SHOPPING  # someone is at the market
    db.flush()

    consume(client, owner, beans["id"])  # 10 -> 9, still above ideal: not added
    for _ in range(8):
        consume(client, owner, beans["id"])  # down to 1, below ideal 2

    view = client.get("/shopping-list", headers=owner).json()
    assert view["status"] == "shopping"
    beans_item = next(i for g in view["groups"] for i in g["items"] if i["name"] == "Beans")
    assert beans_item["status"] == "pending"


def test_consume_does_not_touch_an_item_already_in_the_cart(client, owner, db):
    rice = new_product(client, owner)
    consume(client, owner, rice["id"])
    item = db.scalar(
        select(ShoppingListItem).where(ShoppingListItem.product_id == uuid.UUID(rice["id"]))
    )
    item.status = ShoppingListItemStatus.CHECKED
    db.flush()

    consume(client, owner, rice["id"])  # 5 -> 0

    db.refresh(item)
    assert item.status == ShoppingListItemStatus.CHECKED
    assert item.quantity_needed == Decimal("5")


# --- Undo -----------------------------------------------------------------


def test_undo_restores_stock_and_removes_the_automatic_item(client, owner, db):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]

    response = client.post(f"/consumption-events/{event_id}/undo", headers=owner)

    assert response.status_code == 200
    assert response.json()["product"]["current_quantity"] == 10.0
    assert list_items(client, owner) == []
    assert db.get(ConsumptionEvent, uuid.UUID(event_id)) is None  # mistakes leave no history


def test_undo_twice_is_rejected(client, owner):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]

    client.post(f"/consumption-events/{event_id}/undo", headers=owner)
    second = client.post(f"/consumption-events/{event_id}/undo", headers=owner)

    assert second.status_code == 404


def test_undo_keeps_an_item_added_by_hand(client, owner):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]
    [item] = list_items(client, owner)
    client.patch(f"/shopping-list/items/{item['id']}", json={"quantity_needed": 10}, headers=owner)

    client.post(f"/consumption-events/{event_id}/undo", headers=owner)

    assert [i["quantity_needed"] for i in list_items(client, owner)] == [10.0]


def test_only_who_consumed_can_undo(client, owner):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]
    invite = client.get("/me", headers=owner).json()["household"]["invite_code"]
    partner_token = client.post(
        "/auth/register",
        json={
            "name": "Carol",
            "email": "carol@example.com",
            "password": "correct horse battery",
            "invite_code": invite,
        },
    ).json()["access_token"]

    response = client.post(
        f"/consumption-events/{event_id}/undo",
        headers={"Authorization": f"Bearer {partner_token}"},
    )

    assert response.status_code == 403


def test_undo_expires_after_ten_minutes(client, owner, db):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]
    event = db.get(ConsumptionEvent, uuid.UUID(event_id))
    event.consumed_at = datetime.now(UTC) - timedelta(minutes=11)
    db.flush()

    response = client.post(f"/consumption-events/{event_id}/undo", headers=owner)

    assert response.status_code == 409


def test_cannot_undo_another_households_consumption(client, owner, stranger):
    rice = new_product(client, owner)
    event_id = consume(client, owner, rice["id"]).json()["consumption_event_id"]

    assert client.post(f"/consumption-events/{event_id}/undo", headers=stranger).status_code == 404


# --- Shopping list --------------------------------------------------------


def test_no_list_yet_returns_an_empty_view(client, owner):
    view = client.get("/shopping-list", headers=owner).json()

    assert view["id"] is None
    assert view["groups"] == []


def test_list_sorted_by_market_corridors_with_other_last(client, db):
    headers = demo_headers(client, db)
    market = client.get("/markets", headers=headers).json()[0]

    view = client.get("/shopping-list", params={"market_id": market["id"]}, headers=headers).json()

    names = [group["name"] for group in view["groups"]]
    assert names[0] == "Produce"  # first corridor in walking order
    assert names[-1] == "Other"  # Paper Goods has no corridor in this market
    assert view["groups"][-1]["corridor_id"] is None
    assert view["item_count"] == 15  # products at or under their minimum
    milk = next(i for g in view["groups"] for i in g["items"] if i["name"] == "Whole milk")
    assert milk["last_price_cents"] == 549
    assert milk["brand"] == "Valley Farm"


def test_list_without_market_is_grouped_by_category(client, db):
    headers = demo_headers(client, db)

    view = client.get("/shopping-list", headers=headers).json()

    names = [group["name"] for group in view["groups"]]
    assert names == sorted(names)
    assert all(group["corridor_id"] is None for group in view["groups"])


def test_list_rejects_another_households_market(client, owner, stranger):
    market = client.post("/markets", json={"name": "Mine"}, headers=owner).json()

    response = client.get("/shopping-list", params={"market_id": market["id"]}, headers=stranger)

    assert response.status_code == 404


def test_add_update_and_remove_items_by_hand(client, owner):
    rice = new_product(client, owner)

    added = client.post(
        "/shopping-list/items",
        json={"product_id": rice["id"], "quantity_needed": 10},
        headers=owner,
    )
    assert added.status_code == 201
    [item] = list_items(client, owner)
    assert item["added_manually"] is True

    again = client.post(
        "/shopping-list/items",
        json={"product_id": rice["id"], "quantity_needed": 15},
        headers=owner,
    )
    assert again.status_code == 200  # already on the list: quantity replaced
    assert list_items(client, owner)[0]["quantity_needed"] == 15.0

    patched = client.patch(
        f"/shopping-list/items/{item['id']}", json={"quantity_needed": 5}, headers=owner
    )
    assert patched.status_code == 200

    assert client.delete(f"/shopping-list/items/{item['id']}", headers=owner).status_code == 204
    assert list_items(client, owner) == []


def test_other_households_cannot_touch_list_items(client, owner, stranger):
    rice = new_product(client, owner)
    consume(client, owner, rice["id"])
    [item] = list_items(client, owner)

    patch = client.patch(
        f"/shopping-list/items/{item['id']}", json={"quantity_needed": 99}, headers=stranger
    )
    remove = client.delete(f"/shopping-list/items/{item['id']}", headers=stranger)
    add = client.post(
        "/shopping-list/items",
        json={"product_id": rice["id"], "quantity_needed": 1},
        headers=stranger,
    )

    assert patch.status_code == remove.status_code == add.status_code == 404


# --- Concurrency ----------------------------------------------------------


def test_simultaneous_consumes_are_not_lost():
    """Two people tap "consume" at the same instant, each with their own connection.

    Without the row lock both would read 10 and write 9, losing one consumption.
    Uses committed data, so it cleans up after itself.
    """
    with SessionLocal() as setup:
        household = Household(name="Race", invite_code=f"R{uuid.uuid4().hex[:7].upper()}")
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
        area = StorageArea(household_id=household.id, name="Fridge", position=0)
        category = Category(household_id=household.id, name="Dairy")
        setup.add_all([*users, area, category])
        setup.flush()
        product = Product(
            household_id=household.id,
            category_id=category.id,
            storage_area_id=area.id,
            name="Milk",
            unit=ProductUnit.LITER,
            consume_step=Decimal("1"),
            ideal_quantity=Decimal("2"),
            min_quantity=Decimal("2"),
            current_quantity=Decimal("10"),
        )
        setup.add(product)
        setup.commit()
        household_id, product_id, user_ids = household.id, product.id, [u.id for u in users]

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def tap(user_id):
        try:
            with SessionLocal() as session:
                user = session.get(User, user_id)
                barrier.wait()
                consume_product(session, user, product_id, None)
                session.commit()
        except Exception as error:  # surfaced below
            errors.append(error)

    threads = [threading.Thread(target=tap, args=(user_id,)) for user_id in user_ids]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert errors == []
        with SessionLocal() as check:
            stock = check.get(Product, product_id).current_quantity
            events = check.scalars(
                select(ConsumptionEvent).where(ConsumptionEvent.product_id == product_id)
            ).all()
        assert stock == Decimal("8")
        assert len(events) == 2
    finally:
        with SessionLocal() as cleanup:
            cleanup.execute(delete(Household).where(Household.id == household_id))
            cleanup.commit()
