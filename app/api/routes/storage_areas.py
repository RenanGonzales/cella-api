import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Product, StorageArea
from app.schemas.catalog import (
    StorageAreaCreate,
    StorageAreaOrder,
    StorageAreaOut,
    StorageAreaUpdate,
)
from app.services.catalog import get_owned, name_taken

router = APIRouter(prefix="/storage-areas", tags=["storage areas"])

LABEL = "Storage area"


def _ensure_unique(db: DbSession, user: CurrentUser, name: str, exclude_id=None) -> None:
    if name_taken(db, StorageArea, user.household_id, name, exclude_id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{LABEL} '{name}' already exists")


@router.get("", response_model=list[StorageAreaOut])
def list_storage_areas(user: CurrentUser, db: DbSession) -> list[StorageArea]:
    """Storage areas in grid order."""
    return db.scalars(
        select(StorageArea)
        .where(StorageArea.household_id == user.household_id)
        .order_by(StorageArea.position, StorageArea.name)
    ).all()


@router.post("", response_model=StorageAreaOut, status_code=status.HTTP_201_CREATED)
def create_storage_area(body: StorageAreaCreate, user: CurrentUser, db: DbSession) -> StorageArea:
    """Add a storage area at the end of the grid."""
    _ensure_unique(db, user, body.name)
    last_position = db.scalar(
        select(func.max(StorageArea.position)).where(StorageArea.household_id == user.household_id)
    )
    area = StorageArea(
        household_id=user.household_id,
        name=body.name,
        position=0 if last_position is None else last_position + 1,
    )
    db.add(area)
    db.commit()
    return area


# Declared before "/{area_id}" routes so "order" is not parsed as an id.
@router.put("/order", response_model=list[StorageAreaOut])
def reorder_storage_areas(
    body: StorageAreaOrder, user: CurrentUser, db: DbSession
) -> list[StorageArea]:
    """Set the grid order. The list must contain every storage area of the household once."""
    areas = db.scalars(
        select(StorageArea).where(StorageArea.household_id == user.household_id)
    ).all()
    by_id = {area.id: area for area in areas}

    if len(body.ids) != len(set(body.ids)) or set(body.ids) != set(by_id):
        raise HTTPException(
            422,
            "ids must list every storage area of the household exactly once",
        )

    for position, area_id in enumerate(body.ids):
        by_id[area_id].position = position
    db.commit()
    return [by_id[area_id] for area_id in body.ids]


@router.patch("/{area_id}", response_model=StorageAreaOut)
def update_storage_area(
    area_id: uuid.UUID, body: StorageAreaUpdate, user: CurrentUser, db: DbSession
) -> StorageArea:
    area = get_owned(db, StorageArea, area_id, user.household_id, LABEL)
    if body.name is not None:
        _ensure_unique(db, user, body.name, exclude_id=area.id)
        area.name = body.name
    db.commit()
    return area


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_area(area_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    """Delete an empty storage area. Areas with products (archived included) are kept."""
    area = get_owned(db, StorageArea, area_id, user.household_id, LABEL)
    in_use = db.scalar(select(func.count()).where(Product.storage_area_id == area.id))
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{LABEL} has {in_use} product(s); move them to another area first",
        )
    db.delete(area)
    db.commit()
