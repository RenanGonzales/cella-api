"""Receipts: the demo's sample, reading a photo with Claude (mocked), confirming prices."""

import base64

import pytest

from app.core.config import Settings
from app.services import receipts
from app.services.receipts import receipt_text

PHOTO = {"media_type": "image/jpeg", "data": base64.b64encode(b"fake jpeg bytes").decode()}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def demo(client) -> dict[str, str]:
    return auth(client.post("/auth/demo").json()["access_token"])


def shop(client, headers, how_many: int = 3) -> dict:
    """Start shopping somewhere without a plan, buy a few items, check out."""
    view = client.post("/shopping-list/start", json={"market_id": None}, headers=headers).json()
    items = [item for group in view["groups"] for item in group["items"]][:how_many]
    for item in items:
        client.patch(
            f"/shopping-list/items/{item['id']}", json={"status": "checked"}, headers=headers
        )
    response = client.post("/shopping-list/checkout", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def bought_products(client, headers, purchase_id) -> dict[str, dict]:
    detail = client.get(f"/purchases/{purchase_id}", headers=headers).json()
    return {item["product_id"]: item for item in detail["items"] if item["status"] == "checked"}


def test_receipt_text_looks_printed():
    assert receipt_text("Whole milk", "Valley Farm") == "WHOLE MILK VALLEY FARM"
    assert receipt_text("Laundry detergent", "Sparkle") == "LAUNDRY DETERG. SPARKLE"


def test_sample_receipt_covers_what_was_bought(client):
    headers = demo(client)
    purchase = shop(client, headers)
    bought = bought_products(client, headers, purchase["purchase_id"])

    draft = client.get(f"/purchases/{purchase['purchase_id']}/receipt/sample", headers=headers)
    assert draft.status_code == 200, draft.text
    receipt = draft.json()

    assert receipt["source"] == "sample"
    matched = [line for line in receipt["lines"] if line["product_id"]]
    assert {line["product_id"] for line in matched} == set(bought)
    # Each product was bought last week: the sample shows how its price moved since then.
    assert all(line["previous_price_cents"] for line in matched)
    assert all(line["unit_price_cents"] % 10 == 9 for line in matched)
    # Real receipts carry lines that are not products.
    assert [line["text"] for line in receipt["lines"] if not line["product_id"]] == ["SHOPPING BAG"]
    assert receipt["total_cents"] == sum(line["line_total_cents"] for line in receipt["lines"])
    # Asking again gives the same receipt.
    again = client.get(f"/purchases/{purchase['purchase_id']}/receipt/sample", headers=headers)
    assert again.json() == receipt


def test_confirming_sets_prices_and_the_last_price(client):
    headers = demo(client)
    purchase = shop(client, headers)
    path = f"/purchases/{purchase['purchase_id']}"
    receipt = client.get(f"{path}/receipt/sample", headers=headers).json()
    prices = [
        {"product_id": line["product_id"], "unit_price_cents": line["unit_price_cents"]}
        for line in receipt["lines"]
        if line["product_id"]
    ]

    saved = client.put(
        f"{path}/receipt",
        json={"source": "sample", "total_cents": receipt["total_cents"], "prices": prices},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    detail = saved.json()
    assert detail["receipt_source"] == "sample"
    assert detail["paid_cents"] == receipt["total_cents"] == detail["receipt_total_cents"]
    assert detail["items_without_price"] == 0

    # The confirmed price is now the product's last price.
    first = prices[0]
    product = client.get(f"/products/{first['product_id']}", headers=headers).json()
    assert product["last_price_cents"] == first["unit_price_cents"]


def test_confirm_rejects_products_not_bought_on_the_trip(client):
    headers = demo(client)
    purchase = shop(client, headers, how_many=1)
    bought = set(bought_products(client, headers, purchase["purchase_id"]))
    other = next(
        p["id"] for p in client.get("/products", headers=headers).json() if p["id"] not in bought
    )

    response = client.put(
        f"/purchases/{purchase['purchase_id']}/receipt",
        json={"source": "manual", "prices": [{"product_id": other, "unit_price_cents": 100}]},
        headers=headers,
    )
    assert response.status_code == 422


def test_confirm_rejects_two_prices_for_one_product(client):
    headers = demo(client)
    purchase = shop(client, headers, how_many=1)
    product_id = next(iter(bought_products(client, headers, purchase["purchase_id"])))
    price = {"product_id": product_id, "unit_price_cents": 100}
    response = client.put(
        f"/purchases/{purchase['purchase_id']}/receipt",
        json={"source": "manual", "prices": [price, price]},
        headers=headers,
    )
    assert response.status_code == 422


def test_receipts_of_other_households_are_not_found(client, owner):
    headers = demo(client)
    purchase = shop(client, headers, how_many=1)
    path = f"/purchases/{purchase['purchase_id']}/receipt"
    assert client.get(f"{path}/sample", headers=owner).status_code == 404
    assert (
        client.put(path, json={"source": "manual", "prices": []}, headers=owner).status_code == 404
    )


# --- Reading a photo ------------------------------------------------------------


@pytest.fixture
def ai_settings(settings: Settings) -> Settings:
    settings.receipt_ai_enabled = True
    settings.anthropic_api_key = "test-key"
    settings.receipt_ai_emails = ["Owner@Example.com"]
    return settings


def owner_purchase(client, owner) -> dict:
    """The owner buys two products of their own."""
    ids = {c["name"]: c["id"] for c in client.get("/categories", headers=owner).json()}
    areas = {a["name"]: a["id"] for a in client.get("/storage-areas", headers=owner).json()}
    for name in ("Milk", "Coffee"):
        product = client.post(
            "/products",
            json={
                "name": name,
                "category_id": next(iter(ids.values())),
                "storage_area_id": areas["Pantry"],
                "unit": "un",
                "consume_step": 1,
                "ideal_quantity": 4,
                "current_quantity": 0,
            },
            headers=owner,
        ).json()
        client.post(
            "/shopping-list/items",
            json={"product_id": product["id"], "quantity_needed": 2},
            headers=owner,
        )
    return shop(client, owner, how_many=2)


def test_photo_reading_is_off_by_default(client, owner):
    purchase = owner_purchase(client, owner)
    response = client.post(
        f"/purchases/{purchase['purchase_id']}/receipt/read", json=PHOTO, headers=owner
    )
    assert response.status_code == 403
    assert client.get("/me", headers=owner).json()["features"] == {
        "receipt_ai": False,
        "is_demo": False,
    }


def test_photo_reading_only_for_listed_accounts(client, ai_settings, owner, stranger):
    assert client.get("/me", headers=owner).json()["features"]["receipt_ai"] is True
    assert client.get("/me", headers=stranger).json()["features"]["receipt_ai"] is False


def test_photo_reading_never_on_demo_households(client, ai_settings):
    ai_settings.receipt_ai_emails = []  # even an empty list must not open it
    headers = demo(client)
    purchase = shop(client, headers, how_many=1)
    response = client.post(
        f"/purchases/{purchase['purchase_id']}/receipt/read", json=PHOTO, headers=headers
    )
    assert response.status_code == 403
    assert client.get("/me", headers=headers).json()["features"]["is_demo"] is True


def test_photo_reading_matches_lines_to_products(client, ai_settings, owner, monkeypatch):
    purchase = owner_purchase(client, owner)
    sent = {}

    def fake_claude(settings, media_type, data, prompt):
        sent.update(media_type=media_type, data=data, prompt=prompt)
        return {
            "store_name": "MERCADO BOM PRECO",
            "purchased_on": "2026-10-12",
            "total_cents": 4013,
            "lines": [
                {
                    "text": "LEITE INT 1L",
                    "quantity": 2,
                    "unit_price_cents": 549,
                    "line_total_cents": 1098,
                    "match": 2,
                },
                {
                    "text": "CAFE TORRADO 500G",
                    "quantity": 1,
                    "unit_price_cents": 2900,
                    "line_total_cents": 2900,
                    "match": 1,
                },
                {
                    "text": "LEITE DE NOVO",
                    "quantity": 1,
                    "unit_price_cents": 1,
                    "line_total_cents": 1,
                    "match": 2,
                },  # a second line for the same product
                {
                    "text": "SACOLA",
                    "quantity": 1,
                    "unit_price_cents": 15,
                    "line_total_cents": 15,
                    "match": None,
                },
                {
                    "text": "",
                    "quantity": None,
                    "unit_price_cents": None,
                    "line_total_cents": None,
                    "match": 99,
                },  # junk is dropped
            ],
        }

    monkeypatch.setattr(receipts, "_call_claude", fake_claude)
    response = client.post(
        f"/purchases/{purchase['purchase_id']}/receipt/read", json=PHOTO, headers=owner
    )
    assert response.status_code == 200, response.text
    draft = response.json()

    assert sent["media_type"] == "image/jpeg"
    assert "1. Coffee, unit un" in sent["prompt"] and "2. Milk, unit un" in sent["prompt"]
    assert draft["source"] == "ai"
    assert draft["purchased_on"] == "2026-10-12"
    assert [line["text"] for line in draft["lines"]] == [
        "LEITE INT 1L",
        "CAFE TORRADO 500G",
        "LEITE DE NOVO",
        "SACOLA",
    ]
    products = {p["id"]: p["name"] for p in client.get("/products", headers=owner).json()}
    matched = [products.get(line["product_id"]) for line in draft["lines"]]
    assert matched == ["Milk", "Coffee", None, None]


def test_photo_must_be_a_valid_image_under_5_mb(client, ai_settings, owner):
    purchase = owner_purchase(client, owner)
    path = f"/purchases/{purchase['purchase_id']}/receipt/read"
    bad_type = client.post(path, json={**PHOTO, "media_type": "application/pdf"}, headers=owner)
    assert bad_type.status_code == 422
    bad_data = client.post(path, json={**PHOTO, "data": "not base64!"}, headers=owner)
    assert bad_data.status_code == 422
    huge = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
    too_big = client.post(path, json={**PHOTO, "data": huge}, headers=owner)
    assert too_big.status_code in (413, 422)
