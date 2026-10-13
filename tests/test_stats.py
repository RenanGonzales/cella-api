"""Spending per month, recent consumption and price history."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services.stats import _month_starts


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def demo(client) -> dict[str, str]:
    return auth(client.post("/auth/demo").json()["access_token"])


def test_month_starts_cross_the_year():
    now = datetime(2026, 2, 10, tzinfo=UTC)
    assert [start.strftime("%Y-%m") for start in _month_starts(now, 4)] == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_demo_has_three_months_of_spending(client):
    headers = demo(client)
    response = client.get("/stats/spending", params={"months": 4}, headers=headers)
    assert response.status_code == 200, response.text
    months = response.json()
    assert len(months) == 4
    assert months[-1]["month"] == datetime.now(UTC).strftime("%Y-%m")
    assert sum(month["purchases"] for month in months) == 12
    assert all(month["paid_cents"] > 0 for month in months if month["purchases"])
    purchases = client.get("/purchases", params={"limit": 100}, headers=headers).json()
    assert sum(month["paid_cents"] for month in months) == sum(p["paid_cents"] for p in purchases)


def test_spending_uses_the_receipt_total(client):
    headers = demo(client)
    newest = client.get("/purchases", params={"limit": 1}, headers=headers).json()[0]
    assert newest["receipt_source"] == "sample"
    assert newest["paid_cents"] == newest["receipt_total_cents"] == newest["total_cents"] + 15


def test_spending_months_follow_the_time_zone(client, owner):
    response = client.get(
        "/stats/spending", params={"tz": "America/Sao_Paulo", "months": 1}, headers=owner
    )
    local = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m")
    assert response.json() == [{"month": local, "paid_cents": 0, "purchases": 0}]
    assert (
        client.get("/stats/spending", params={"tz": "Mars/Base"}, headers=owner).status_code == 422
    )


def test_consumption_of_the_last_days(client):
    headers = demo(client)
    milk = next(
        p for p in client.get("/products", headers=headers).json() if p["name"] == "Whole milk"
    )
    before = client.get("/stats/consumption", params={"days": 1}, headers=headers).json()
    client.post(f"/products/{milk['id']}/consume", headers=headers)
    client.post(f"/products/{milk['id']}/consume", headers=headers)

    after = client.get("/stats/consumption", params={"days": 1}, headers=headers).json()
    assert after["times"] == before["times"] + 2
    entry = next(p for p in after["products"] if p["name"] == "Whole milk")
    assert entry["times"] >= 2 and entry["unit"] == "l"
    week = client.get("/stats/consumption", headers=headers).json()
    assert week["days"] == 7
    assert [p["times"] for p in week["products"]] == sorted(
        (p["times"] for p in week["products"]), reverse=True
    )


def test_price_history_oldest_first(client, stranger):
    headers = demo(client)
    milk = next(
        p for p in client.get("/products", headers=headers).json() if p["name"] == "Whole milk"
    )
    points = client.get(f"/products/{milk['id']}/prices", headers=headers).json()
    assert len(points) >= 2
    dates = [point["purchased_at"] for point in points]
    assert dates == sorted(dates)
    assert points[-1]["unit_price_cents"] == milk["last_price_cents"] == 549
    assert client.get(f"/products/{milk['id']}/prices", headers=stranger).status_code == 404
