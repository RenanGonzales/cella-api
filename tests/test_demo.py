"""Public demo: every visitor gets a private copy of the demo household."""

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import func, select

from app.models import Household
from app.services.demo import PRODUCTS, delete_expired_sandboxes
from scripts.seed import create_demo, reset_demo


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def start_demo(client) -> dict:
    response = client.post("/auth/demo")
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_creates_a_private_household_with_two_people(client):
    session = start_demo(client)

    alex = client.get("/me", headers=auth(session["access_token"])).json()
    sam = client.get("/me", headers=auth(session["partner"]["access_token"])).json()

    assert alex["name"] == "Alex"
    assert sam["name"] == "Sam" == session["partner"]["name"]
    assert sam["id"] == session["partner"]["id"]
    assert alex["household"]["id"] == sam["household"]["id"]
    assert [member["name"] for member in alex["household"]["members"]] == ["Alex", "Sam"]

    headers = auth(session["access_token"])
    assert len(client.get("/products", headers=headers).json()) == len(PRODUCTS)
    shopping_list = client.get("/shopping-list", headers=headers).json()
    assert shopping_list["status"] == "open"
    assert shopping_list["item_count"] == 15


def test_two_visitors_never_see_each_other(client):
    first, second = start_demo(client), start_demo(client)
    first_headers, second_headers = auth(first["access_token"]), auth(second["access_token"])

    milk = next(
        product
        for product in client.get("/products", headers=first_headers).json()
        if product["name"] == "Whole milk"
    )
    client.post(f"/products/{milk['id']}/consume", headers=first_headers)

    first_me = client.get("/me", headers=first_headers).json()
    second_me = client.get("/me", headers=second_headers).json()
    assert first_me["household"]["id"] != second_me["household"]["id"]
    second_milk = next(
        product
        for product in client.get("/products", headers=second_headers).json()
        if product["name"] == "Whole milk"
    )
    assert second_milk["current_quantity"] == milk["current_quantity"]
    # Ids of one copy are invisible to the other one.
    assert client.get(f"/products/{milk['id']}", headers=second_headers).status_code == 404


def test_demo_tokens_last_as_long_as_the_copy(client, settings):
    session = start_demo(client)

    payload = jwt.decode(
        session["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    assert session["expires_in"] == settings.demo_ttl_hours * 3600
    assert payload["exp"] - payload["iat"] == settings.demo_ttl_hours * 3600


def test_expired_copies_are_deleted_and_their_tokens_stop_working(client, db):
    old = start_demo(client)
    household_id = client.get("/me", headers=auth(old["access_token"])).json()["household"]["id"]
    household = db.get(Household, household_id)
    household.demo_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    start_demo(client)  # the next visitor triggers the cleanup

    db.expire_all()
    assert db.get(Household, household_id) is None
    assert client.get("/me", headers=auth(old["access_token"])).status_code == 401


def test_cleanup_keeps_real_and_local_demo_households(client, db, owner):
    reset_demo(db)
    local_demo = create_demo(db)
    db.flush()

    # Even far in the future, only demo copies expire (other sandboxes may exist in the
    # database, so the test checks what must survive rather than a count).
    delete_expired_sandboxes(db, datetime.now(UTC) + timedelta(days=365))

    db.expire_all()
    assert db.get(Household, local_demo.id) is not None
    assert client.get("/me", headers=owner).status_code == 200


def test_live_copies_are_capped(client, db, settings):
    live = db.scalar(select(func.count()).where(Household.demo_expires_at.is_not(None)))
    settings.demo_max_sandboxes = live + 1
    start_demo(client)

    response = client.post("/auth/demo")

    assert response.status_code == 503


def test_nobody_can_join_a_demo_copy_with_an_invite_code(client, db):
    session = start_demo(client)
    code = client.get("/me", headers=auth(session["access_token"])).json()["household"][
        "invite_code"
    ]
    assert db.scalar(select(Household.demo_expires_at).where(Household.invite_code == code))

    response = client.post(
        "/auth/register",
        json={
            "name": "Mallory",
            "email": "mallory@example.com",
            "password": "correct horse battery",
            "invite_code": code,
        },
    )

    assert response.status_code == 404
