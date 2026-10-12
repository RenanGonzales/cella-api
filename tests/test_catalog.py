from app.domain.defaults import DEFAULT_CATEGORIES, DEFAULT_STORAGE_AREAS
from scripts.seed import create_demo, reset_demo


def ids_by_name(client, path, headers) -> dict[str, str]:
    return {item["name"]: item["id"] for item in client.get(path, headers=headers).json()}


def new_product(client, headers, **overrides) -> dict:
    areas = ids_by_name(client, "/storage-areas", headers)
    categories = ids_by_name(client, "/categories", headers)
    body = {
        "name": "Whole milk",
        "brand": "Valley Farm",
        "category_id": categories["Dairy"],
        "storage_area_id": areas["Fridge"],
        "unit": "l",
        "consume_step": 1,
        "ideal_quantity": 6,
        "current_quantity": 2,
    }
    body.update(overrides)
    response = client.post("/products", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- Defaults -------------------------------------------------------------


def test_new_household_gets_default_areas_and_categories(client, owner):
    areas = client.get("/storage-areas", headers=owner).json()
    categories = client.get("/categories", headers=owner).json()

    assert [area["name"] for area in areas] == DEFAULT_STORAGE_AREAS
    assert sorted(category["name"] for category in categories) == sorted(DEFAULT_CATEGORIES)


# --- Storage areas --------------------------------------------------------


def test_create_rename_and_delete_storage_area(client, owner):
    created = client.post("/storage-areas", json={"name": "Garage"}, headers=owner).json()
    assert created["position"] == len(DEFAULT_STORAGE_AREAS)  # appended at the end

    renamed = client.patch(
        f"/storage-areas/{created['id']}", json={"name": "Garage shelf"}, headers=owner
    )
    assert renamed.json()["name"] == "Garage shelf"

    assert client.delete(f"/storage-areas/{created['id']}", headers=owner).status_code == 204
    assert "Garage shelf" not in ids_by_name(client, "/storage-areas", owner)


def test_storage_area_names_are_unique_ignoring_case(client, owner):
    response = client.post("/storage-areas", json={"name": "pantry"}, headers=owner)

    assert response.status_code == 409


def test_reorder_storage_areas(client, owner):
    areas = client.get("/storage-areas", headers=owner).json()
    reversed_ids = [area["id"] for area in reversed(areas)]

    response = client.put("/storage-areas/order", json={"ids": reversed_ids}, headers=owner)

    assert response.status_code == 200
    names = [area["name"] for area in client.get("/storage-areas", headers=owner).json()]
    assert names == list(reversed(DEFAULT_STORAGE_AREAS))


def test_reorder_requires_every_area_exactly_once(client, owner):
    ids = [area["id"] for area in client.get("/storage-areas", headers=owner).json()]

    missing_one = client.put("/storage-areas/order", json={"ids": ids[:-1]}, headers=owner)
    duplicated = client.put("/storage-areas/order", json={"ids": [*ids, ids[0]]}, headers=owner)

    assert missing_one.status_code == duplicated.status_code == 422


def test_cannot_delete_storage_area_in_use(client, owner):
    product = new_product(client, owner)

    response = client.delete(f"/storage-areas/{product['storage_area_id']}", headers=owner)

    assert response.status_code == 409


# --- Categories -----------------------------------------------------------


def test_category_crud_and_in_use_protection(client, owner):
    created = client.post("/categories", json={"name": "Pet Food"}, headers=owner).json()
    duplicate = client.post("/categories", json={"name": "PET FOOD"}, headers=owner)
    assert duplicate.status_code == 409

    new_product(client, owner, name="Cat food", category_id=created["id"])
    assert client.delete(f"/categories/{created['id']}", headers=owner).status_code == 409


# --- Products -------------------------------------------------------------


def test_create_product_returns_computed_fields(client, owner):
    product = new_product(client, owner)

    assert product["below_ideal"] is True  # 2 of 6 liters
    assert product["consume_step"] == 1.0  # quantities are JSON numbers
    assert product["last_price_cents"] is None  # never bought yet


def test_update_product_only_changes_sent_fields(client, owner):
    product = new_product(client, owner)

    updated = client.patch(
        f"/products/{product['id']}", json={"current_quantity": 6, "brand": None}, headers=owner
    ).json()

    assert updated["current_quantity"] == 6.0
    assert updated["below_ideal"] is False
    assert updated["brand"] is None  # brand can be cleared
    assert updated["name"] == "Whole milk"  # untouched


def test_update_product_rejects_null_for_required_fields(client, owner):
    product = new_product(client, owner)

    response = client.patch(f"/products/{product['id']}", json={"name": None}, headers=owner)

    assert response.status_code == 422


def test_product_quantities_are_validated(client, owner):
    areas = ids_by_name(client, "/storage-areas", owner)
    categories = ids_by_name(client, "/categories", owner)
    body = {
        "name": "Rice",
        "category_id": categories["Grains & Pasta"],
        "storage_area_id": areas["Pantry"],
        "unit": "kg",
        "ideal_quantity": 5,
    }

    zero_step = client.post("/products", json={**body, "consume_step": 0}, headers=owner)
    negative = client.post(
        "/products", json={**body, "consume_step": 5, "current_quantity": -1}, headers=owner
    )
    bad_unit = client.post(
        "/products", json={**body, "consume_step": 5, "unit": "box"}, headers=owner
    )

    assert zero_step.status_code == negative.status_code == bad_unit.status_code == 422


def test_list_filters(client, owner):
    areas = ids_by_name(client, "/storage-areas", owner)
    new_product(client, owner)  # milk: fridge, below ideal
    new_product(
        client,
        owner,
        name="Shampoo",
        brand="Bright",
        storage_area_id=areas["Bathroom"],
        category_id=ids_by_name(client, "/categories", owner)["Personal Care"],
        unit="un",
        ideal_quantity=1,
        current_quantity=1,
    )

    def names(**params):
        response = client.get("/products", params=params, headers=owner)
        return [product["name"] for product in response.json()]

    assert names() == ["Shampoo", "Whole milk"]
    assert names(storage_area_id=areas["Bathroom"]) == ["Shampoo"]
    assert names(below_ideal=True) == ["Whole milk"]
    assert names(q="bright") == ["Shampoo"]  # matches brand, case-insensitive


def test_archive_hides_product_and_restore_brings_it_back(client, owner):
    product = new_product(client, owner)

    archived = client.post(f"/products/{product['id']}/archive", headers=owner).json()
    assert archived["archived_at"] is not None
    assert client.get("/products", headers=owner).json() == []
    assert (
        len(client.get("/products", params={"include_archived": True}, headers=owner).json()) == 1
    )

    restored = client.post(f"/products/{product['id']}/restore", headers=owner).json()
    assert restored["archived_at"] is None


def test_last_price_comes_from_the_latest_archived_purchase(client, db):
    reset_demo(db)
    create_demo(db)
    db.flush()
    headers = {"Authorization": f"Bearer {client.post('/auth/demo').json()['access_token']}"}

    milk = client.get("/products", params={"q": "Whole milk"}, headers=headers).json()[0]

    assert milk["last_price_cents"] == 549
    assert milk["last_purchased_at"] is not None


# --- Isolation between households ----------------------------------------


def test_other_households_cannot_read_or_change_a_product(client, owner, stranger):
    product = new_product(client, owner)
    url = f"/products/{product['id']}"

    assert client.get(url, headers=stranger).status_code == 404
    assert client.patch(url, json={"name": "Hacked"}, headers=stranger).status_code == 404
    assert client.post(f"{url}/archive", headers=stranger).status_code == 404
    assert client.get("/products", headers=stranger).json() == []
    assert client.get(url, headers=owner).json()["name"] == "Whole milk"


def test_cannot_use_another_households_category_or_area(client, owner, stranger):
    owner_categories = ids_by_name(client, "/categories", owner)
    owner_areas = ids_by_name(client, "/storage-areas", owner)

    foreign_category = client.post(
        "/products",
        json={
            "name": "Sneaky",
            "category_id": owner_categories["Dairy"],
            "storage_area_id": ids_by_name(client, "/storage-areas", stranger)["Fridge"],
            "unit": "un",
            "consume_step": 1,
            "ideal_quantity": 1,
        },
        headers=stranger,
    )
    foreign_area_rename = client.patch(
        f"/storage-areas/{owner_areas['Fridge']}", json={"name": "Mine"}, headers=stranger
    )

    assert foreign_category.status_code == 404
    assert foreign_area_rename.status_code == 404


def test_household_members_share_the_catalog(client, owner):
    product = new_product(client, owner)
    invite_code = client.get("/me", headers=owner).json()["household"]["invite_code"]
    member = client.post(
        "/auth/register",
        json={
            "name": "Carol",
            "email": "carol@example.com",
            "password": "correct horse battery",
            "invite_code": invite_code,
        },
    ).json()["access_token"]

    response = client.get(
        f"/products/{product['id']}", headers={"Authorization": f"Bearer {member}"}
    )

    assert response.status_code == 200
