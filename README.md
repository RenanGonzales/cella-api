# Cella API

Backend for **Cella**, a household supplies manager. Track what you have at home, turn what runs out into a shopping list sorted by the aisles of *your* store, and split the shopping route between the people going to the market.

> The name comes from the Latin *cella*, the Roman pantry.

**Status:** in development (MVP)

## Stack

- Python + FastAPI
- PostgreSQL + SQLAlchemy + Alembic
- Pytest
- Docker Compose or Homebrew (local development)
- AWS EC2 + Nginx (deployment)

## MVP features

- Household inventory, organized by storage area (fridge, pantry, bathroom, laundry...)
- One-tap consumption that updates stock and adds the item to the shopping list
- Shopping list sorted by the corridors of the selected market
- List split between household members by blocks of neighboring corridors
- Minimum (reorder point) and ideal stock per product
- In-store checkout: confirm quantities, update stock, archive the list, carry over what was missing
- Purchase history with totals; prices filled in at home
- Purchase and consumption history stored for future analytics (monthly spending, price tracking, stock autonomy)

## Getting started

Requirements: Python 3.12+ and PostgreSQL 16, either installed with Homebrew (macOS) or running in Docker.

**1. Database**

Option A, Homebrew:

```bash
brew install python@3.12 postgresql@16
brew services start postgresql@16
$(brew --prefix postgresql@16)/bin/psql postgres \
  -c "CREATE ROLE cella LOGIN PASSWORD 'cella';" \
  -c "CREATE DATABASE cella OWNER cella;"
```

Option B, Docker:

```bash
docker compose up -d
```

**2. API**

```bash
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
alembic upgrade head                 # create the schema
python -m scripts.seed               # local demo household (login: alex@demo.cella.app / demo1234)
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

## API

| Method | Route | Description |
|---|---|---|
| POST | `/auth/register` | Create an account and a household, or join one with an invite code |
| POST | `/auth/login` | Log in with email and password |
| POST | `/auth/demo` | Start a private demo: a copy of the demo household for this visitor, with tokens for Alex and Sam (when `DEMO_ENABLED=true`) |
| GET | `/me` | Logged-in user, household and members |
| GET, POST | `/storage-areas` | List or create storage areas (fridge, pantry...) |
| PATCH, DELETE | `/storage-areas/{id}` | Rename or delete an empty storage area |
| PUT | `/storage-areas/order` | Reorder the home grid |
| GET, POST | `/categories` | List or create categories |
| PATCH, DELETE | `/categories/{id}` | Rename or delete an unused category |
| GET, POST | `/products` | List (with filters) or create products |
| GET, PATCH | `/products/{id}` | Read or partially update a product |
| POST | `/products/{id}/archive`, `/restore` | Hide a product without losing its history, or bring it back |
| GET, POST | `/markets` | List or create markets |
| GET, PATCH, DELETE | `/markets/{id}` | Read, update, or delete a market never used for shopping |
| POST | `/markets/{id}/archive`, `/restore` | Hide a market while keeping its prices, or bring it back |
| GET, PUT | `/markets/{id}/layout` | Read or save (all at once) the corridors and their categories |
| POST | `/products/{id}/consume` | Consume one step (or a quantity); updates the shopping list |
| POST | `/consumption-events/{id}/undo` | Undo a mistaken consume (10 minutes, same user) |
| GET | `/shopping-list` | Active list, grouped by a market's corridors (`?market_id=`) or by category; `?mine=true` for your route |
| POST | `/shopping-list/items` | Add a product by hand |
| PATCH, DELETE | `/shopping-list/items/{id}` | Change quantity; in the store, check, mark not found or reassign; or remove |
| POST | `/shopping-list/start`, `/cancel` | Start shopping at a market, or leave without buying |
| POST | `/shopping-list/split` | Split the route between people by blocks of corridors |
| POST | `/shopping-list/checkout` | Finish: stock updated, list archived, missing items carried over |
| GET | `/purchases`, `/purchases/{id}` | Purchase history with totals |
| PATCH | `/purchases/{id}/items/{item_id}` | Fill in the price paid |
| GET | `/health` | Status and version |

Protected routes expect `Authorization: Bearer <token>`. Interactive docs at `/docs`.

Checks (tests need the database running):

```bash
ruff check . && ruff format --check .
pytest
```

## Project structure

```text
app/
  api/        routes and request dependencies (current user)
  core/       settings, database session, security helpers
  schemas/    request and response models
  services/   queries shared by routes (household ownership, last price)
  domain/     business rules with no database access (restock, rounding, route split, invite codes)
  models/     SQLAlchemy models, grouped by domain
alembic/      database migrations
scripts/      local demo seed, cleanup of expired demo copies
tests/
```

## Documentation

- [Data model](docs/data-model.md)
- [Security](docs/security.md)
- [Changelog](CHANGELOG.md)

## Related

- Frontend: [cella-web](../cella-web)
- Project page: https://renangonzales.com/cella

## License

© 2026 Renan Gonzales. All rights reserved.

The source code is public for viewing and evaluation only. No permission is granted to use, copy, modify or distribute it without prior written consent.
