# Cella API

Backend for **Cella**, a household supplies manager. Track what you have at home, turn what runs out into a shopping list sorted by the aisles of *your* store, and split the shopping route between the people going to the market.

> The name comes from the Latin *cella*, the Roman pantry.

**Status:** in development (MVP)

## Stack

- Python + FastAPI
- PostgreSQL + SQLAlchemy + Alembic
- Pytest
- Docker Compose (local development)
- AWS EC2 + Nginx (deployment)

## MVP features

- Household inventory, organized by storage area (fridge, pantry, bathroom, laundry...)
- One-tap consumption that updates stock and adds the item to the shopping list
- Shopping list sorted by the corridors of the selected market
- List split between household members by blocks of neighboring corridors
- In-store checkout: confirm quantities, update stock, archive the list
- Purchase and consumption history stored for future analytics (monthly spending, price tracking, stock autonomy)

## Getting started

Requirements: Python 3.12+, Docker.

```bash
cp .env.example .env
docker compose up -d                 # PostgreSQL 16
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                 # create the schema
python -m scripts.seed               # demo household (login: alex@demo.cella.app / demo1234)
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

Checks:

```bash
ruff check . && ruff format --check .
pytest
```

## Project structure

```text
app/
  core/       settings and database session
  domain/     business rules with no database access (e.g. purchase rounding)
  models/     SQLAlchemy models, grouped by domain
alembic/      database migrations
scripts/      demo seed (also used as the daily demo reset)
tests/
```

## Documentation

- [Data model](docs/data-model.md)

## Related

- Frontend: [cella-web](../cella-web)
- Project page: https://renangonzales.com/cella

## License

© 2026 Renan Gonzales. All rights reserved.

The source code is public for viewing and evaluation only. No permission is granted to use, copy, modify or distribute it without prior written consent.
