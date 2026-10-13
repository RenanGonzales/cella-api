# Data model

Conventions:

- Primary keys: UUID
- Timestamps: `timestamptz`
- Quantities: `numeric(10,3)`
- Money: integer cents (R$ 5,49 = `549`)
- Every household-scoped query is filtered by the current user's `household_id`

## Tables

```text
households
  id, name, invite_code (unique), created_at

users
  id, household_id -> households, name, email (unique), password_hash, created_at

storage_areas                      -- fridge, pantry, bathroom, laundry...
  id, household_id -> households, name, position
  unique (household_id, lower(name))

categories                         -- dairy, cleaning... (maps to a corridor)
  id, household_id -> households, name
  unique (household_id, lower(name))

products
  id, household_id -> households,
  category_id -> categories, storage_area_id -> storage_areas,
  name, brand (nullable), unit (un | kg | g | l | ml),
  consume_step, min_quantity, ideal_quantity, current_quantity,
  archived_at (nullable), created_at

consumption_events                 -- history for stock autonomy forecasts
  id, product_id -> products, user_id -> users (nullable), quantity, consumed_at

markets                            -- a store as one household knows it
  id, household_id -> households, name, chain (nullable), address (nullable),
  archived_at (nullable), created_at,
  plan_cols, plan_rows (nullable)  -- floor plan grid; null = plain list of corridors
  route_style                      -- column | block (zigzag with two blocks of aisles)

corridors                          -- a piece of the floor plan
  id, market_id -> markets, name, position (walking order),
  kind                             -- aisle | wall | island | entrance | checkout
  x, y, w, h (nullable)            -- place on the grid, in cells

corridor_categories                -- category -> corridor, per market
  id, market_id -> markets, corridor_id -> corridors, category_id -> categories
  unique (market_id, category_id)

shopping_lists
  id, household_id -> households, market_id -> markets (nullable until shopping starts),
  status (open | shopping | archived), created_at, started_at, completed_at

shopping_list_items
  id, shopping_list_id -> shopping_lists, product_id -> products,
  quantity_needed, quantity_bought (nullable),
  unit_price_cents (nullable), status (pending | checked | not_found),
  added_manually (bool), assigned_user_id -> users (nullable)
  unique (shopping_list_id, product_id)
```

A product's "last price" is not stored: it is the `unit_price_cents` from its most recent archived purchase.

## Business rules

1. **Consume:** `current_quantity -= consume_step` (never below zero) and a `consumption_event` is recorded. When stock reaches the minimum (`current_quantity <= min_quantity` and below the ideal), the item is created or updated in the active list with `quantity_needed = ideal_quantity - current_quantity`, rounded up to whole packages (`consume_step` is the package size). Example: milk with ideal 6 and minimum 2 goes on the list at 2, asking for 4. `min_quantity` defaults to the ideal. See `app/domain/stock.py`.
2. **One active list per household:** at most one list with status `open` or `shopping`, enforced by a partial unique index. Consuming during shopping adds the item to the list in progress as `pending`.
3. **Start shopping:** a market is selected, the list becomes `shopping` and is sorted by `corridors.position`. Categories without a corridor in that market go to an "Other" group at the end.
4. **Split:** `assigned_user_id` is filled by blocks of neighboring corridors, minimizing the largest number of items any one person gets (linear partition, `app/domain/split.py`). A corridor is never split; items in the cart keep their person; it can be changed by hand.
5. **Checkout:** `checked` items add `quantity_bought` to stock. The list becomes `archived`. `not_found` and `pending` items are carried over to a new `open` list.
6. **Fine-tuning at home:** brand and `unit_price_cents` are edited on the archived list.
7. **Archive product:** sets `archived_at`. The product disappears from the UI and its history is kept.
8. **New household:** starts with default storage areas and categories (`app/domain/defaults.py`), named in English and translated by the frontend.
9. **Delete storage area or category:** only when no product (archived included) uses it; otherwise `409`.
10. **Market layout:** saved as a whole (`PUT /markets/{id}/layout`) in one transaction. Corridors sent with an id keep it; corridors left out are deleted; a category is in at most one corridor per market.
11. **Floor plan:** with `plan`, every corridor has a place on the grid (inside it, never overlapping another one); entrance and checkout appear at most once and hold no categories. The order sent is the walking order: the web editor computes a zigzag from the entrance (column by column, or block by block in stores with a cross aisle) or takes the order picked by hand. The API checks the geometry; the shopping list only needs `position`.
11. **Delete market:** only if it was never used for shopping; otherwise archive it to keep its prices.

12. **Manual items win:** an item added or edited by hand (`added_manually`) is never lowered or removed by consume or undo.
13. **Undo:** within 10 minutes and only by the person who consumed. Restores stock, shrinks or removes the automatic pending item, and deletes the event (a mistaken tap is not consumption).

## Concurrency

**Lock order.** Every transaction that changes stock locks the household's active list first and then the products, in id order: consume, undo and checkout. One shared order means two transactions can never wait on each other in a cycle (deadlock).

**Checkout.** The list row is locked, so if two phones tap "finish" together, one checkout archives the list and the other gets `409`; stock is added once. Covered by `tests/test_store.py::test_two_phones_finishing_at_once_add_stock_only_once`, which fails without the lock.

**Consume.** Consume and undo lock the product row (`SELECT ... FOR UPDATE`) for the length of the transaction. Two people tapping "consume" on the same product at the same instant are serialized: without the lock, both would read the same stock and one consumption would be lost. `tests/test_shopping.py::test_simultaneous_consumes_are_not_lost` runs two real connections in parallel and fails if the lock is removed.

Creating the active list on first use relies on the partial unique index: if two requests try to create it at once, one wins and the other reuses it.

## Shared markets (planned)

Today a market belongs to one household, because its layout maps that household's own categories. The model is prepared for sharing layouts between households that shop at the same store:

1. **Store identity.** `chain` and `address` already identify the physical store. A global `stores` table, keyed by a place id (Google Places or OpenStreetMap), will deduplicate stores typed in different ways; `markets.store_id` will point to it.
2. **Common category language.** Every household starts with the same default categories (`app/domain/defaults.py`). Importing a layout from another household of the same store copies corridors and maps categories **by name**, so no global category table is needed.
3. **Crowd corrections.** With several households per store, the most common corridor order and mapping can be suggested to new users, removing the setup step entirely.

