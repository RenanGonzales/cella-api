"""Market floor plans: modules on a grid, entrance and checkout, walking order."""

import pytest

from tests.test_markets import category_ids, new_market


def piece(name, x, y, w=1, h=5, kind="aisle", category_ids=()):
    return {
        "name": name,
        "kind": kind,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "category_ids": list(category_ids),
    }


def put_plan(client, headers, market_id, corridors, cols=12, rows=8, route_style="column"):
    return client.put(
        f"/markets/{market_id}/layout",
        json={
            "plan": {"cols": cols, "rows": rows},
            "route_style": route_style,
            "corridors": corridors,
        },
        headers=headers,
    )


def demo_headers(client):
    return {"Authorization": f"Bearer {client.post('/auth/demo').json()['access_token']}"}


def test_demo_market_comes_with_a_floor_plan(client):
    headers = demo_headers(client)
    market = client.get("/markets", headers=headers).json()[0]

    layout = client.get(f"/markets/{market['id']}/layout", headers=headers).json()

    assert market["has_plan"] is True
    assert market["corridor_count"] == 10  # entrance and checkout are not corridors
    assert layout["plan"] == {"cols": 21, "rows": 10}
    assert layout["route_style"] == "column"
    kinds = [corridor["kind"] for corridor in layout["corridors"]]
    assert kinds[0] == "entrance" and kinds[-1] == "checkout"
    assert {"aisle", "wall", "island"} <= set(kinds)
    assert all(corridor["w"] and corridor["h"] for corridor in layout["corridors"])
    # The shopping list still follows the walking order.
    groups = client.get("/shopping-list", params={"market_id": market["id"]}, headers=headers)
    assert groups.json()["groups"][0]["name"] == "Produce"


def test_saves_a_wholesale_plan_with_two_blocks(client, owner):
    market = new_market(client, owner)
    categories = category_ids(client, owner)
    aisles = [piece(f"Back {n}", 1 + 2 * n, 1) for n in range(8)]
    aisles += [piece(f"Front {n}", 1 + 2 * n, 7) for n in range(8)]
    corridors = [
        piece("Entrance", 0, 13, 3, 1, "entrance"),
        piece("Fruit", 17, 1, 2, 2, "island", [categories["Produce"]]),
        *aisles,
        piece("Checkout", 9, 13, 7, 1, "checkout"),
    ]

    response = put_plan(client, owner, market["id"], corridors, 21, 14, "block")

    assert response.status_code == 200, response.text
    layout = response.json()
    assert layout["plan"] == {"cols": 21, "rows": 14}
    assert layout["route_style"] == "block"
    assert [c["name"] for c in layout["corridors"]][:3] == ["Entrance", "Fruit", "Back 0"]
    fruit = layout["corridors"][1]
    assert (fruit["kind"], fruit["x"], fruit["y"], fruit["w"], fruit["h"]) == (
        "island",
        17,
        1,
        2,
        2,
    )
    assert [category["name"] for category in fruit["categories"]] == ["Produce"]
    saved = client.get(f"/markets/{market['id']}", headers=owner).json()
    assert saved["corridor_count"] == 17
    assert saved["has_plan"] is True


def test_moving_and_resizing_keeps_corridor_ids(client, owner):
    market = new_market(client, owner)
    first = put_plan(client, owner, market["id"], [piece("A", 1, 1)]).json()
    corridor = first["corridors"][0]

    moved = put_plan(
        client, owner, market["id"], [{**piece("A", 4, 2, 2, 3, "wall"), "id": corridor["id"]}]
    ).json()

    assert moved["corridors"][0]["id"] == corridor["id"]
    assert (moved["corridors"][0]["x"], moved["corridors"][0]["w"]) == (4, 2)
    assert moved["corridors"][0]["kind"] == "wall"


@pytest.mark.parametrize(
    ("corridors", "message"),
    [
        ([piece("A", 11, 1, 2, 2)], "outside the plan"),
        ([piece("A", 1, 1, 2, 5), piece("B", 2, 3)], "overlaps"),
        ([{"name": "A", "x": 1, "y": 1}], "required with a plan"),
        ([piece("In", 0, 7, 2, 1, "entrance"), piece("In 2", 3, 7, 2, 1, "entrance")], "Only one"),
    ],
)
def test_rejects_invalid_plans(client, owner, corridors, message):
    market = new_market(client, owner)

    response = put_plan(client, owner, market["id"], corridors)

    assert response.status_code == 422
    assert message in response.text


def test_entrance_cannot_hold_categories(client, owner):
    market = new_market(client, owner)
    categories = category_ids(client, owner)

    response = put_plan(
        client, owner, market["id"], [piece("In", 0, 7, 2, 1, "entrance", [categories["Dairy"]])]
    )

    assert response.status_code == 422


@pytest.mark.parametrize(("cols", "rows"), [(3, 8), (41, 8), (12, 31)])
def test_plan_size_has_limits(client, owner, cols, rows):
    market = new_market(client, owner)

    assert put_plan(client, owner, market["id"], [], cols, rows).status_code == 422


def test_placing_corridors_needs_a_plan(client, owner):
    market = new_market(client, owner)

    response = client.put(
        f"/markets/{market['id']}/layout",
        json={"corridors": [piece("A", 1, 1)]},
        headers=owner,
    )

    assert response.status_code == 422


def test_saving_a_plain_list_removes_the_plan(client, owner):
    market = new_market(client, owner)
    put_plan(client, owner, market["id"], [piece("A", 1, 1)])

    response = client.put(
        f"/markets/{market['id']}/layout",
        json={"corridors": [{"name": "A"}]},
        headers=owner,
    )

    assert response.status_code == 200
    assert response.json()["plan"] is None
    assert response.json()["corridors"][0]["x"] is None
    assert client.get(f"/markets/{market['id']}", headers=owner).json()["has_plan"] is False
