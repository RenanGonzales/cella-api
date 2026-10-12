from app.domain.defaults import DEFAULT_CATEGORIES
from scripts.seed import create_demo, reset_demo


def category_ids(client, headers) -> dict[str, str]:
    return {item["name"]: item["id"] for item in client.get("/categories", headers=headers).json()}


def new_market(client, headers, **overrides) -> dict:
    body = {"name": "Neighborhood Market", "chain": "Angeloni", "address": "Rua X, 100"}
    body.update(overrides)
    response = client.post("/markets", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def put_layout(client, headers, market_id, corridors):
    return client.put(
        f"/markets/{market_id}/layout", json={"corridors": corridors}, headers=headers
    )


# --- Markets --------------------------------------------------------------


def test_create_and_update_market(client, owner):
    market = new_market(client, owner)
    assert market["chain"] == "Angeloni"
    assert market["corridor_count"] == 0

    updated = client.patch(
        f"/markets/{market['id']}",
        json={"address": None, "name": "Angeloni Kobrasol"},
        headers=owner,
    ).json()

    assert updated["name"] == "Angeloni Kobrasol"
    assert updated["address"] is None  # optional fields can be cleared
    assert updated["chain"] == "Angeloni"  # untouched


def test_market_name_cannot_be_cleared(client, owner):
    market = new_market(client, owner)

    response = client.patch(f"/markets/{market['id']}", json={"name": None}, headers=owner)

    assert response.status_code == 422


def test_archive_hides_market_from_picker(client, owner):
    market = new_market(client, owner)

    client.post(f"/markets/{market['id']}/archive", headers=owner)

    assert client.get("/markets", headers=owner).json() == []
    assert len(client.get("/markets", params={"include_archived": True}, headers=owner).json()) == 1


def test_market_with_purchase_history_cannot_be_deleted(client, db):
    reset_demo(db)
    create_demo(db)
    db.flush()
    headers = {"Authorization": f"Bearer {client.post('/auth/demo').json()['access_token']}"}
    demo_market = client.get("/markets", headers=headers).json()[0]

    response = client.delete(f"/markets/{demo_market['id']}", headers=headers)

    assert response.status_code == 409


def test_unused_market_can_be_deleted(client, owner):
    market = new_market(client, owner)

    assert client.delete(f"/markets/{market['id']}", headers=owner).status_code == 204


# --- Layout ---------------------------------------------------------------


def test_new_market_has_every_category_unmapped(client, owner):
    market = new_market(client, owner)

    layout = client.get(f"/markets/{market['id']}/layout", headers=owner).json()

    assert layout["corridors"] == []
    assert len(layout["unmapped_categories"]) == len(DEFAULT_CATEGORIES)


def test_put_layout_saves_corridors_in_order(client, owner):
    market = new_market(client, owner)
    categories = category_ids(client, owner)

    response = put_layout(
        client,
        owner,
        market["id"],
        [
            {"name": "Produce", "category_ids": [categories["Produce"]]},
            {"name": "Dairy & Frozen", "category_ids": [categories["Dairy"], categories["Frozen"]]},
        ],
    )

    assert response.status_code == 200
    layout = response.json()
    assert [corridor["name"] for corridor in layout["corridors"]] == ["Produce", "Dairy & Frozen"]
    assert [corridor["position"] for corridor in layout["corridors"]] == [0, 1]
    assert {c["name"] for c in layout["corridors"][1]["categories"]} == {"Dairy", "Frozen"}
    assert len(layout["unmapped_categories"]) == len(DEFAULT_CATEGORIES) - 3
    assert client.get(f"/markets/{market['id']}", headers=owner).json()["corridor_count"] == 2


def test_put_layout_keeps_ids_reorders_and_deletes(client, owner):
    market = new_market(client, owner)
    categories = category_ids(client, owner)
    first = put_layout(
        client,
        owner,
        market["id"],
        [
            {"name": "A", "category_ids": [categories["Produce"]]},
            {"name": "B", "category_ids": [categories["Bakery"]]},
            {"name": "C", "category_ids": []},
        ],
    ).json()
    a, b, _ = first["corridors"]

    second = put_layout(
        client,
        owner,
        market["id"],
        [
            {"id": b["id"], "name": "B renamed", "category_ids": [categories["Bakery"]]},
            {
                "id": a["id"],
                "name": "A",
                "category_ids": [categories["Produce"], categories["Dairy"]],
            },
        ],
    ).json()

    assert [(c["id"], c["name"]) for c in second["corridors"]] == [
        (b["id"], "B renamed"),
        (a["id"], "A"),
    ]  # same ids, new order, C deleted
    assert {c["name"] for c in second["corridors"][1]["categories"]} == {"Dairy", "Produce"}


def test_put_layout_rejects_a_category_in_two_corridors(client, owner):
    market = new_market(client, owner)
    dairy = category_ids(client, owner)["Dairy"]

    response = put_layout(
        client,
        owner,
        market["id"],
        [{"name": "A", "category_ids": [dairy]}, {"name": "B", "category_ids": [dairy]}],
    )

    assert response.status_code == 422


def test_put_layout_rejects_duplicate_corridor_names(client, owner):
    market = new_market(client, owner)

    response = put_layout(client, owner, market["id"], [{"name": "Dairy"}, {"name": "dairy"}])

    assert response.status_code == 422


def test_failed_layout_save_changes_nothing(client, owner):
    market = new_market(client, owner)
    categories = category_ids(client, owner)
    put_layout(client, owner, market["id"], [{"name": "A", "category_ids": [categories["Dairy"]]}])
    before = client.get(f"/markets/{market['id']}/layout", headers=owner).json()

    response = put_layout(
        client,
        owner,
        market["id"],
        [
            {"name": "New", "category_ids": [categories["Produce"]]},
            {"id": "00000000-0000-0000-0000-000000000000", "name": "Ghost"},
        ],
    )

    assert response.status_code == 404
    assert client.get(f"/markets/{market['id']}/layout", headers=owner).json() == before


# --- Isolation between households ----------------------------------------


def test_other_households_cannot_see_or_edit_a_market(client, owner, stranger):
    market = new_market(client, owner)
    url = f"/markets/{market['id']}"

    assert client.get(url, headers=stranger).status_code == 404
    assert client.get(f"{url}/layout", headers=stranger).status_code == 404
    assert put_layout(client, stranger, market["id"], []).status_code == 404
    assert client.get("/markets", headers=stranger).json() == []


def test_layout_cannot_use_another_households_categories(client, owner, stranger):
    market = new_market(client, stranger)
    owner_dairy = category_ids(client, owner)["Dairy"]

    response = put_layout(
        client, stranger, market["id"], [{"name": "Sneaky", "category_ids": [owner_dairy]}]
    )

    assert response.status_code == 404
