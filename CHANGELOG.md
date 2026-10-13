# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

While the MVP is in progress, versions stay at `0.x`: each delivered block bumps the minor version and fixes bump the patch version. `1.0.0` is the public launch.

## [Unreleased]

## [0.10.0] - 2026-10-13

Receipts, spending and history.

### Added

- Receipts of past purchases:
  - `GET /purchases/{id}/receipt/sample`: a believable receipt for what was bought (store-style names, prices that moved a little since the last visit, a line that is not a product). The same purchase always gives the same receipt.
  - `POST /purchases/{id}/receipt/read`: reads a photo with Claude (Haiku by default) and suggests a product of the household for each line, with the previous price. Off by default; only for the emails in `RECEIPT_AI_EMAILS`, never for demo households. The photo is not stored.
  - `PUT /purchases/{id}/receipt`: saves the reviewed prices (only products bought on that trip, one price each) and the total paid. The prices become each product's last price.
- `GET /stats/spending`: paid per month in a time zone, months without purchases included.
- `GET /stats/consumption`: what was used in the last days, most used first.
- `GET /products/{id}/prices`: prices paid in the last purchases, for a price chart.
- `GET /me` reports `features` (`receipt_ai`, `is_demo`).
- Purchases report `receipt_source`, `receipt_total_cents` and `paid_cents`.
- The demo household now has three months of purchases (12 trips, some without a market), with prices a little lower in the past.
- Docs: [decision on reading receipts with Claude](docs/decisions/receipt-reading.md) and [cost to run](docs/cost-to-run.md).
- Settings: `RECEIPT_AI_ENABLED`, `ANTHROPIC_API_KEY`, `RECEIPT_AI_MODEL`, `RECEIPT_AI_EMAILS`.
- Tests: 147 in total (the Claude call is replaced in tests, so they cost nothing).

### Migration

- `b7c1d2e3f4a5`: `shopping_lists.receipt_source` and `receipt_total_cents`.

## [0.9.0] - 2026-10-12

### Added

- Shopping list items carry the product's stock (`current_quantity`, `min_quantity`, `ideal_quantity`), so the list can show why an item is there and how much is enough.
- Shopping without a market: `POST /shopping-list/start` accepts `market_id: null` (or no body field). The list is then grouped by category, and splitting the route gives each person whole categories, balanced by number of items.
- Tests: 130 in total.

## [0.8.0] - 2026-10-12

Market floor plans.

### Added

- A market can have a floor plan: a grid (4 to 40 cells wide, 4 to 30 deep) where each corridor has a kind (`aisle`, `wall`, `island`, `entrance`, `checkout`) and a place (`x`, `y`, `w`, `h`). `GET/PUT /markets/{id}/layout` read and save it with `plan` and `route_style` (`column` or `block`).
- Validation: pieces inside the grid and never overlapping, all placed or none, at most one entrance and one checkout, which hold no categories.
- `MarketOut.has_plan`; `corridor_count` leaves the entrance and checkout out.
- The demo market comes with a plan (21 x 10, zigzag from the entrance).
- Migration `878621be9a28` (existing markets stay plain lists, existing corridors become aisles).
- Tests: 126 in total.

### Changed

- Up to 100 corridors per market (was 60), for big wholesale stores.

### Fixed

- Two demo tests no longer depend on other demo copies existing in the same database.

## [0.7.0] - 2026-10-12

A private demo per visitor, so several people can try Cella at the same time.

### Changed

- `POST /auth/demo` now creates a private copy of the demo household for each visitor (same data: Alex and Sam, 35 products, a market with 10 corridors, an open list of 15 items) and returns a token for Alex plus a `partner` with Sam's token, so the frontend can show two phones.
- Demo copies and their tokens expire after `DEMO_TTL_HOURS` (24 by default). Expired copies are deleted when the next demo starts; `scripts/cleanup_demo.py` does the same for a cron job.
- The demo household data moved to `app/services/demo.py`; `scripts/seed.py` keeps creating the local demo with fixed logins for development.

### Added

- `households.demo_expires_at` (migration `3e8fd442e752`), null for real households.
- `DEMO_MAX_SANDBOXES` (500 by default): new demos get `503` while that many copies are live.
- Tests for the isolation between visitors, expiry, cleanup, the cap and invite codes (113 tests).

### Security

- Demo copies cannot be joined with their invite code, so no real account ends up in a household that is deleted the next day.
- Demo people have a random, never-revealed password: the copies can only be entered through their own tokens.

## [0.6.0] - 2026-10-12

Completes the backend of the MVP.

### Added

- Minimum stock (reorder point): `min_quantity` on products. A product goes on the shopping list when its stock reaches the minimum, and the list asks for enough to get back to the ideal. Defaults to the ideal quantity; existing products keep their behavior (migration `5a4ed3d47a10` backfills it).
- `needs_restock` on products and a `needs_restock` filter on `GET /products`.
- In-store flow: `POST /shopping-list/start` (choose the market), `POST /shopping-list/cancel` (back to open, nothing lost).
- `POST /shopping-list/split`: each person gets a block of neighboring corridors with a balanced number of items (linear partition, dynamic programming, checked against brute force). A corridor is never split.
- `GET /shopping-list?mine=true`: only the items assigned to the logged-in person.
- `PATCH /shopping-list/items/{id}` also sets `status` (checked, not found, pending), `quantity_bought` (defaults to the quantity needed) and `assigned_user_id`.
- `POST /shopping-list/checkout`: bought items go into stock, the list is archived, and items not found or still pending move to a new open list.
- Purchases: `GET /purchases` (history with totals and items still without a price), `GET /purchases/{id}`, `PATCH /purchases/{id}/items/{item_id}` to fill in prices at home.
- Lock ordering (active list first, then products by id) shared by consume, undo and checkout, to prevent deadlocks. A second simultaneous checkout gets `409` and stock is added once; covered by a test with two real connections, which fails without the lock.
- 28 new tests (107 in total).

### Changed

- Automatic list updates follow the minimum instead of the ideal; undo removes the automatic item once stock is back above the minimum.
- While shopping, the list is sorted by the chosen market by default.
- Demo products have a minimum of half their ideal (whole units for countable items).

## [0.5.0] - 2026-10-12

### Added

- `POST /products/{id}/consume`: one tap removes one consume step (or a given `quantity`) from stock; stock never goes below zero and the consumption event records only what was really removed.
- The shopping list fills itself: when stock falls below the ideal, the product is added (or its quantity raised) in whole packages. Lists are created on first use.
- `POST /consumption-events/{id}/undo`: undo a mistaken tap within 10 minutes, only by who consumed; restores stock, shrinks or removes the automatic list item and deletes the event.
- `GET /shopping-list`: active list grouped by the chosen market's corridors in walking order (unmapped categories in "Other", last), or by category; each item carries brand and last price.
- Shopping list items by hand: add, change quantity, remove. Items added or edited by hand are never lowered or removed by automatic updates (`added_manually`, migration `eb459f002aab`).
- Consuming while someone is at the market adds the item to the list in progress as pending; items already in the cart are left alone.
- Row lock (`SELECT ... FOR UPDATE`) on consume and undo, so simultaneous taps on the same product are never lost. Covered by a test with two real concurrent connections, which fails without the lock.
- 22 new tests (79 in total).

## [0.4.0] - 2026-10-12

### Added

- Markets: list, create, partial update, archive, restore and delete (only when never used for shopping).
- `chain` and `address` on markets to identify the physical store, preparing layouts to be shared between households (migration `c623b4059b21`).
- Market layout: `GET /markets/{id}/layout` returns corridors in walking order with their categories, plus unmapped categories; `PUT /markets/{id}/layout` saves the whole layout in one transaction.
- Layout rules: a category in at most one corridor per market, unique corridor names, kept corridors keep their ids, categories must belong to the household.
- `docs/data-model.md`: planned path for shared markets.
- 13 new tests (57 in total).

### Changed

- A request that fails rolls back its database session explicitly.

## [0.3.0] - 2026-10-12

### Added

- Storage areas: list, create, rename, delete and `PUT /storage-areas/order` to reorder the home grid.
- Categories: list, create, rename and delete.
- Products: list with filters (storage area, category, below ideal stock, search by name or brand, archived), read, create, partial update, archive and restore.
- Each product returns its last price paid and purchase date, computed from archived shopping lists.
- New households start with 5 default storage areas and 13 default categories (English names, translated by the frontend).
- Storage area and category names are unique per household, ignoring case (migration `e2f8861952e1`).
- Storage areas and categories in use cannot be deleted (`409`).
- Household isolation: rows of another household answer `404`, including ids sent as references (category, storage area).
- 17 new tests (44 in total), including isolation between households.

### Changed

- The demo seed reuses the default storage areas and categories.

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

[Unreleased]: https://github.com/RenanGonzales/cella-api/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/RenanGonzales/cella-api/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/RenanGonzales/cella-api/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/RenanGonzales/cella-api/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/RenanGonzales/cella-api/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/RenanGonzales/cella-api/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/RenanGonzales/cella-api/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/RenanGonzales/cella-api/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/RenanGonzales/cella-api/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/RenanGonzales/cella-api/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RenanGonzales/cella-api/releases/tag/v0.1.0
