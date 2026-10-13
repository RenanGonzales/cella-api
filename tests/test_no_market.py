"""Shopping list details: each item's stock, and shopping without a saved market."""

from tests.test_store import add_to_list, join, new_product


def items(list_json) -> list[dict]:
    return [item for group in list_json["groups"] for item in group["items"]]


def test_items_show_the_products_stock(client, owner):
    milk = new_product(
        client, owner, "Milk", "Dairy", ideal_quantity=6, min_quantity=2, current_quantity=1
    )
    add_to_list(client, owner, milk, 5)

    item = items(client.get("/shopping-list", headers=owner).json())[0]

    assert (item["current_quantity"], item["min_quantity"], item["ideal_quantity"]) == (1, 2, 6)


def test_shopping_without_a_market_groups_by_category(client, owner):
    for name, category in (("Milk", "Dairy"), ("Soap", "Cleaning")):
        add_to_list(client, owner, new_product(client, owner, name, category))

    response = client.post("/shopping-list/start", json={"market_id": None}, headers=owner)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "shopping"
    assert body["market_id"] is None
    assert [group["name"] for group in body["groups"]] == ["Cleaning", "Dairy"]


def test_start_body_can_be_empty(client, owner):
    add_to_list(client, owner, new_product(client, owner, "Milk", "Dairy"))

    assert client.post("/shopping-list/start", json={}, headers=owner).status_code == 200


def test_split_without_a_market_gives_whole_categories(client, owner):
    sam = join(client, owner, "Sam")
    me = client.get("/me", headers=owner).json()["id"]
    sam_id = client.get("/me", headers=sam).json()["id"]
    for name, category in (
        ("Bread", "Bakery"),
        ("Cake", "Bakery"),
        ("Soap", "Cleaning"),
        ("Milk", "Dairy"),
        ("Cheese", "Dairy"),
    ):
        add_to_list(client, owner, new_product(client, owner, name, category))
    client.post("/shopping-list/start", json={}, headers=owner)

    response = client.post("/shopping-list/split", json={"user_ids": [me, sam_id]}, headers=owner)

    assert response.status_code == 200, response.text
    owners = {}
    for group in response.json()["groups"]:
        people = {item["assigned_user_id"] for item in group["items"]}
        assert len(people) == 1, group["name"]  # a category is never split
        owners[group["name"]] = people.pop()
    # Alphabetical walk, balanced: Bakery (2) + Cleaning (1) | Dairy (2).
    assert owners == {"Bakery": me, "Cleaning": me, "Dairy": sam_id}
