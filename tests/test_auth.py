from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import DEFAULT_JWT_SECRET, Settings

PASSWORD = "correct horse battery"


def register(client, **overrides):
    body = {
        "name": "Renan",
        "email": "renan@example.com",
        "password": PASSWORD,
        "household_name": "Home",
    }
    body.update(overrides)
    return client.post("/auth/register", json=body)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Register -------------------------------------------------------------


def test_register_creates_household_and_logs_in(client):
    response = register(client)

    assert response.status_code == 201
    token = response.json()["access_token"]

    me = client.get("/me", headers=auth_header(token)).json()
    assert me["email"] == "renan@example.com"
    assert me["household"]["name"] == "Home"
    assert len(me["household"]["invite_code"]) == 8
    assert [member["name"] for member in me["household"]["members"]] == ["Renan"]


def test_register_joins_household_with_invite_code(client):
    owner_token = register(client).json()["access_token"]
    invite_code = client.get("/me", headers=auth_header(owner_token)).json()["household"][
        "invite_code"
    ]

    response = register(
        client,
        name="Carol",
        email="carol@example.com",
        household_name=None,
        invite_code=invite_code.lower(),  # codes are case-insensitive
    )

    assert response.status_code == 201
    me = client.get("/me", headers=auth_header(response.json()["access_token"])).json()
    assert {member["name"] for member in me["household"]["members"]} == {"Renan", "Carol"}


def test_register_rejects_unknown_invite_code(client):
    response = register(client, household_name=None, invite_code="NOPE1234")

    assert response.status_code == 404


def test_register_rejects_duplicate_email_case_insensitive(client):
    register(client)
    response = register(client, email="RENAN@example.com")

    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},  # under 8 characters
        {"password": "a" * 73},  # over bcrypt's 72-byte limit
        {"household_name": None},  # neither create nor join
        {"invite_code": "ABCD2345"},  # both create and join
        {"email": "not-an-email"},
    ],
)
def test_register_validates_input(client, overrides):
    assert register(client, **overrides).status_code == 422


# --- Login ----------------------------------------------------------------


def test_login_with_correct_password(client):
    register(client)

    response = client.post("/auth/login", json={"email": "Renan@Example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_login_errors_do_not_reveal_which_emails_exist(client):
    register(client)

    wrong_password = client.post(
        "/auth/login", json={"email": "renan@example.com", "password": "wrong password"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong password"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


# --- Protected routes -----------------------------------------------------


def test_me_requires_a_token(client):
    assert client.get("/me").status_code == 401


def test_me_rejects_a_tampered_token(client):
    token = register(client).json()["access_token"]

    assert client.get("/me", headers=auth_header(token + "x")).status_code == 401


def test_me_rejects_an_expired_token(client, settings):
    token = register(client).json()["access_token"]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    payload["exp"] = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    assert client.get("/me", headers=auth_header(expired)).status_code == 401


def test_me_rejects_a_token_signed_with_another_secret(client, settings):
    token = register(client).json()["access_token"]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    forged = jwt.encode(
        payload, "an-attacker-secret-that-is-long-enough", algorithm=settings.jwt_algorithm
    )

    assert client.get("/me", headers=auth_header(forged)).status_code == 401


# --- Demo -----------------------------------------------------------------


def test_demo_login_is_disabled_by_default(client, settings):
    settings.demo_enabled = False

    assert client.post("/auth/demo").status_code == 404


# --- Settings -------------------------------------------------------------


@pytest.mark.parametrize("secret", [DEFAULT_JWT_SECRET, "too-short"])
def test_production_refuses_weak_jwt_secrets(secret):
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret=secret)
