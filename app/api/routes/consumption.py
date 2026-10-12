import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.routes.products import read_product_out
from app.schemas.shopping import ConsumeRequest, ConsumeResponse, UndoResponse
from app.services.shopping import consume_product, undo_consumption

router = APIRouter(tags=["consumption"])


@router.post("/products/{product_id}/consume", response_model=ConsumeResponse)
def consume(
    product_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    body: ConsumeRequest | None = None,
) -> ConsumeResponse:
    """One tap on the home grid: remove one consume step (or `quantity`) from stock.

    If the stock falls below the ideal, the product goes on the shopping list.
    """
    product, event, consumed, on_list = consume_product(
        db, user, product_id, body.quantity if body else None
    )
    event_id = event.id if event is not None else None
    db.commit()
    return ConsumeResponse(
        product=read_product_out(db, user, product.id),
        consumption_event_id=event_id,
        consumed=consumed,
        added_to_list=on_list,
    )


@router.post("/consumption-events/{event_id}/undo", response_model=UndoResponse)
def undo(event_id: uuid.UUID, user: CurrentUser, db: DbSession) -> UndoResponse:
    """Undo a mistaken tap: within 10 minutes, and only by the person who consumed."""
    product, restored = undo_consumption(db, user, event_id)
    db.commit()
    return UndoResponse(product=read_product_out(db, user, product.id), restored=restored)
