import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.domain.stock import needs_restock
from app.models import Category, Product, StorageArea
from app.schemas.catalog import ProductCreate, ProductOut, ProductUpdate
from app.schemas.stats import PricePoint
from app.services.catalog import get_owned, products_with_last_price
from app.services.stats import price_history

router = APIRouter(prefix="/products", tags=["products"])

LABEL = "Product"


def _to_out(product: Product, last_price_cents: int | None, last_purchased_at) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        brand=product.brand,
        category_id=product.category_id,
        storage_area_id=product.storage_area_id,
        unit=product.unit,
        consume_step=product.consume_step,
        ideal_quantity=product.ideal_quantity,
        min_quantity=product.min_quantity,
        current_quantity=product.current_quantity,
        below_ideal=product.current_quantity < product.ideal_quantity,
        needs_restock=needs_restock(
            product.current_quantity, product.min_quantity, product.ideal_quantity
        ),
        last_price_cents=last_price_cents,
        last_purchased_at=last_purchased_at,
        archived_at=product.archived_at,
    )


def read_product_out(db: DbSession, user: CurrentUser, product_id: uuid.UUID) -> ProductOut:
    """A household product with its computed fields (below ideal, last price)."""
    row = db.execute(
        products_with_last_price(user.household_id).where(Product.id == product_id)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{LABEL} not found")
    return _to_out(*row)


def _check_references(
    db: DbSession,
    user: CurrentUser,
    category_id: uuid.UUID | None,
    storage_area_id: uuid.UUID | None,
) -> None:
    """Category and storage area must belong to the same household (blocks cross-household ids)."""
    if category_id is not None:
        get_owned(db, Category, category_id, user.household_id, "Category")
    if storage_area_id is not None:
        get_owned(db, StorageArea, storage_area_id, user.household_id, "Storage area")


@router.get("", response_model=list[ProductOut])
def list_products(
    user: CurrentUser,
    db: DbSession,
    storage_area_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    below_ideal: bool = Query(False, description="Only products under their ideal stock"),
    needs_restock_only: bool = Query(
        False, alias="needs_restock", description="Only products that reached their minimum"
    ),
    q: str | None = Query(None, max_length=100, description="Search by name or brand"),
    include_archived: bool = False,
) -> list[ProductOut]:
    query = products_with_last_price(user.household_id)

    if not include_archived:
        query = query.where(Product.archived_at.is_(None))
    if storage_area_id is not None:
        query = query.where(Product.storage_area_id == storage_area_id)
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if below_ideal:
        query = query.where(Product.current_quantity < Product.ideal_quantity)
    if needs_restock_only:
        query = query.where(
            Product.current_quantity <= Product.min_quantity,
            Product.current_quantity < Product.ideal_quantity,
        )
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(Product.name.ilike(pattern) | Product.brand.ilike(pattern))

    rows = db.execute(query.order_by(Product.name)).all()
    return [_to_out(*row) for row in rows]


@router.get("/{product_id}", response_model=ProductOut)
def read_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    return read_product_out(db, user, product_id)


@router.get("/{product_id}/prices", response_model=list[PricePoint])
def read_prices(
    product_id: uuid.UUID, user: CurrentUser, db: DbSession, limit: int = Query(12, ge=1, le=52)
) -> list[PricePoint]:
    """Prices paid for the product in its last purchases, oldest first."""
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    return price_history(db, product, limit)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, user: CurrentUser, db: DbSession) -> ProductOut:
    _check_references(db, user, body.category_id, body.storage_area_id)
    values = body.model_dump()
    if values["min_quantity"] is None:
        values["min_quantity"] = values["ideal_quantity"]
    product = Product(household_id=user.household_id, **values)
    db.add(product)
    db.commit()
    return read_product_out(db, user, product.id)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID, body: ProductUpdate, user: CurrentUser, db: DbSession
) -> ProductOut:
    """Change only the fields sent. Send `"brand": null` to remove the brand."""
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    changes = body.model_dump(exclude_unset=True)
    _check_references(db, user, changes.get("category_id"), changes.get("storage_area_id"))

    ideal = changes.get("ideal_quantity", product.ideal_quantity)
    minimum = changes.get("min_quantity", product.min_quantity)
    if minimum > ideal:
        raise HTTPException(422, "min_quantity cannot be greater than ideal_quantity")

    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    return read_product_out(db, user, product.id)


@router.post("/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    """Hide a product from the app while keeping its purchase and consumption history."""
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    if product.archived_at is None:
        product.archived_at = datetime.now(UTC)
        db.commit()
    return read_product_out(db, user, product.id)


@router.post("/{product_id}/restore", response_model=ProductOut)
def restore_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    product.archived_at = None
    db.commit()
    return read_product_out(db, user, product.id)
