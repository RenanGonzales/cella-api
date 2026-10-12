import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Category, Corridor, CorridorCategory, Market
from app.schemas.catalog import CategoryOut
from app.schemas.market import LayoutCorridorOut, LayoutIn, LayoutOut


def corridor_counts(db: Session, market_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(Corridor.market_id, func.count())
        .where(Corridor.market_id.in_(market_ids))
        .group_by(Corridor.market_id)
    ).all()
    return dict(rows)


def read_layout(db: Session, market: Market) -> LayoutOut:
    corridors = db.scalars(
        select(Corridor).where(Corridor.market_id == market.id).order_by(Corridor.position)
    ).all()
    mappings = db.execute(
        select(CorridorCategory.corridor_id, Category)
        .join(Category, Category.id == CorridorCategory.category_id)
        .where(CorridorCategory.market_id == market.id)
        .order_by(Category.name)
    ).all()

    by_corridor: dict[uuid.UUID, list[CategoryOut]] = {corridor.id: [] for corridor in corridors}
    mapped_ids: set[uuid.UUID] = set()
    for corridor_id, category in mappings:
        by_corridor[corridor_id].append(CategoryOut(id=category.id, name=category.name))
        mapped_ids.add(category.id)

    all_categories = db.scalars(
        select(Category).where(Category.household_id == market.household_id).order_by(Category.name)
    ).all()

    return LayoutOut(
        market_id=market.id,
        corridors=[
            LayoutCorridorOut(
                id=corridor.id,
                name=corridor.name,
                position=corridor.position,
                categories=by_corridor[corridor.id],
            )
            for corridor in corridors
        ],
        unmapped_categories=[
            CategoryOut(id=category.id, name=category.name)
            for category in all_categories
            if category.id not in mapped_ids
        ],
    )


def replace_layout(db: Session, market: Market, layout: LayoutIn) -> None:
    """Replace corridors, their order and category mapping in one transaction.

    Corridors sent with an id are kept (renamed and moved); corridors left out are deleted.
    The caller commits, so either the whole layout is saved or nothing is.
    """
    existing = {
        corridor.id: corridor
        for corridor in db.scalars(select(Corridor).where(Corridor.market_id == market.id))
    }

    unknown = [c.id for c in layout.corridors if c.id is not None and c.id not in existing]
    if unknown:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Corridor {unknown[0]} not found in this market"
        )

    # Every category must belong to the market's household (blocks cross-household ids).
    requested = {cid for corridor in layout.corridors for cid in corridor.category_ids}
    if requested:
        owned = set(
            db.scalars(
                select(Category.id).where(
                    Category.id.in_(requested), Category.household_id == market.household_id
                )
            )
        )
        if requested - owned:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    # Clear the old mapping first so the (market, category) unique constraint never clashes.
    db.execute(delete(CorridorCategory).where(CorridorCategory.market_id == market.id))

    kept_ids = {c.id for c in layout.corridors if c.id is not None}
    for corridor_id, corridor in existing.items():
        if corridor_id not in kept_ids:
            db.delete(corridor)
    db.flush()

    for position, item in enumerate(layout.corridors):
        if item.id is not None:
            corridor = existing[item.id]
            corridor.name = item.name
            corridor.position = position
        else:
            corridor = Corridor(market_id=market.id, name=item.name, position=position)
            db.add(corridor)
            db.flush()

        db.add_all(
            CorridorCategory(market_id=market.id, corridor_id=corridor.id, category_id=cid)
            for cid in item.category_ids
        )
