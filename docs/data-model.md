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

categories                         -- dairy, cleaning... (maps to a corridor)
  id, household_id -> households, name

products
  id, household_id -> households,
  category_id -> categories, storage_area_id -> storage_areas,
  name, brand (nullable), unit (un | kg | g | l | ml),
  consume_step, ideal_quantity, current_quantity,
  archived_at (nullable), created_at

consumption_events                 -- history for stock autonomy forecasts
  id, product_id -> products, user_id -> users (nullable), quantity, consumed_at

markets
  id, household_id -> households, name

corridors
  id, market_id -> markets, name, position

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
  assigned_user_id -> users (nullable)
  unique (shopping_list_id, product_id)
```

A product's "last price" is not stored: it is the `unit_price_cents` from its most recent archived purchase.

## Business rules

1. **Consume:** `current_quantity -= consume_step` (never below zero) and a `consumption_event` is recorded. If `current_quantity < ideal_quantity`, the item is created or updated in the active list with `quantity_needed = ideal_quantity - current_quantity`, rounded up to whole packages (`consume_step` is the package size). Example: 3 kg missing, 5 kg package -> 5 kg. See `app/domain/stock.py`.
2. **One active list per household:** at most one list with status `open` or `shopping`, enforced by a partial unique index. Consuming during shopping adds the item to the list in progress as `pending`.
3. **Start shopping:** a market is selected, the list becomes `shopping` and is sorted by `corridors.position`. Categories without a corridor in that market go to an "Other" group at the end.
4. **Split:** `assigned_user_id` is filled by blocks of neighboring corridors, balancing the number of items. It can be changed manually.
5. **Checkout:** `checked` items add `quantity_bought` to stock. The list becomes `archived`. `not_found` and `pending` items are carried over to a new `open` list.
6. **Fine-tuning at home:** brand and `unit_price_cents` are edited on the archived list.
7. **Archive product:** sets `archived_at`. The product disappears from the UI and its history is kept.
