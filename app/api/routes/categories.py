import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Product
from app.schemas.catalog import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.catalog import get_owned, name_taken

router = APIRouter(prefix="/categories", tags=["categories"])

LABEL = "Category"


def _ensure_unique(db: DbSession, user: CurrentUser, name: str, exclude_id=None) -> None:
    if name_taken(db, Category, user.household_id, name, exclude_id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{LABEL} '{name}' already exists")


@router.get("", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DbSession) -> list[Category]:
    return db.scalars(
        select(Category).where(Category.household_id == user.household_id).order_by(Category.name)
    ).all()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, user: CurrentUser, db: DbSession) -> Category:
    _ensure_unique(db, user, body.name)
    category = Category(household_id=user.household_id, name=body.name)
    db.add(category)
    db.commit()
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID, body: CategoryUpdate, user: CurrentUser, db: DbSession
) -> Category:
    category = get_owned(db, Category, category_id, user.household_id, LABEL)
    if body.name is not None:
        _ensure_unique(db, user, body.name, exclude_id=category.id)
        category.name = body.name
    db.commit()
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    """Delete an unused category (its corridor mappings in every market go with it)."""
    category = get_owned(db, Category, category_id, user.household_id, LABEL)
    in_use = db.scalar(select(func.count()).where(Product.category_id == category.id))
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{LABEL} has {in_use} product(s); move them to another category first",
        )
    db.delete(category)
    db.commit()
