import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Product, StorageArea
from app.schemas.catalog import ProductCreate, ProductOut, ProductUpdate
from app.services.catalog import get_owned, products_with_last_price

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
        current_quantity=product.current_quantity,
        below_ideal=product.current_quantity < product.ideal_quantity,
        last_price_cents=last_price_cents,
        last_purchased_at=last_purchased_at,
        archived_at=product.archived_at,
    )


def _read(db: DbSession, user: CurrentUser, product_id: uuid.UUID) -> ProductOut:
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
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(Product.name.ilike(pattern) | Product.brand.ilike(pattern))

    rows = db.execute(query.order_by(Product.name)).all()
    return [_to_out(*row) for row in rows]


@router.get("/{product_id}", response_model=ProductOut)
def read_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    return _read(db, user, product_id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, user: CurrentUser, db: DbSession) -> ProductOut:
    _check_references(db, user, body.category_id, body.storage_area_id)
    product = Product(household_id=user.household_id, **body.model_dump())
    db.add(product)
    db.commit()
    return _read(db, user, product.id)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID, body: ProductUpdate, user: CurrentUser, db: DbSession
) -> ProductOut:
    """Change only the fields sent. Send `"brand": null` to remove the brand."""
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    changes = body.model_dump(exclude_unset=True)
    _check_references(db, user, changes.get("category_id"), changes.get("storage_area_id"))

    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    return _read(db, user, product.id)


@router.post("/{product_id}/archive", response_model=ProductOut)
def archive_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    """Hide a product from the app while keeping its purchase and consumption history."""
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    if product.archived_at is None:
        product.archived_at = datetime.now(UTC)
        db.commit()
    return _read(db, user, product.id)


@router.post("/{product_id}/restore", response_model=ProductOut)
def restore_product(product_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProductOut:
    product = get_owned(db, Product, product_id, user.household_id, LABEL)
    product.archived_at = None
    db.commit()
    return _read(db, user, product.id)
