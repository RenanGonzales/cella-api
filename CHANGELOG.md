# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

While the MVP is in progress, versions stay at `0.x`: each delivered block bumps the minor version and fixes bump the patch version. `1.0.0` is the public launch.

## [Unreleased]

## [0.1.0] - 2026-10-12

### Added

- Project setup: FastAPI app, settings from `.env`, SQLAlchemy session, Docker Compose for PostgreSQL 16, Dockerfile.
- Data model with 11 tables: households, users, storage areas, categories, products, consumption events, markets, corridors, corridor categories, shopping lists and shopping list items.
- Database rules: one active shopping list per household (partial unique index), non-negative quantities and prices, enum values checked by the database.
- First Alembic migration with deterministic constraint names.
- Purchase rounding rule: missing stock is rounded up to whole packages (`app/domain/stock.py`).
- Demo seed: household with 2 members, 35 products, 1 market with 10 corridors, a past purchase with prices and an open shopping list. Idempotent, so it doubles as the daily demo reset.
- `GET /health` reporting status and version.
- CI on GitHub Actions: lint, migrations, seed and tests on every push.
- Documentation: README and data model.

[Unreleased]: https://github.com/RenanGonzales/cella-api/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/RenanGonzales/cella-api/releases/tag/v0.1.0
