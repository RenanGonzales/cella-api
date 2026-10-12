# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

While the MVP is in progress, versions stay at `0.x`: each delivered block bumps the minor version and fixes bump the patch version. `1.0.0` is the public launch.

## [Unreleased]

## [0.2.0] - 2026-10-12

### Added

- Authentication with email and password: `POST /auth/register`, `POST /auth/login`.
- Sign-up creates a new household or joins an existing one with its invite code, in a single step.
- `POST /auth/demo`: log in as the demo household without a password (only when `DEMO_ENABLED=true`).
- `GET /me`: logged-in user, household, invite code and members.
- `get_current_user` dependency: every protected route is scoped to the user's household.
- JWT access tokens (HS256, 7 days); bcrypt password hashing with the 72-byte limit validated explicitly.
- Login errors and response times that do not reveal which emails are registered.
- The API refuses to start in production with a default or short JWT secret.
- CORS for the local Vite dev server.
- Test suite against PostgreSQL with per-test rollback (27 tests).
- `docs/security.md`: implemented protections, known trade-offs and production roadmap.

### Changed

- Demo household identifiers moved to `app/core/demo.py`, shared by the seed and the demo login.

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

[Unreleased]: https://github.com/RenanGonzales/cella-api/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/RenanGonzales/cella-api/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RenanGonzales/cella-api/releases/tag/v0.1.0
