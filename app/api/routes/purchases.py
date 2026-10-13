import base64
import binascii
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import Household
from app.schemas.receipt import MAX_IMAGE_BYTES, ReceiptConfirm, ReceiptDraft, ReceiptImage
from app.schemas.shopping import PurchaseDetail, PurchaseItemUpdate, PurchaseSummary
from app.services.purchases import get_purchase, list_purchases, purchase_detail, set_price
from app.services.receipts import (
    ai_reading_allowed,
    confirm_receipt,
    read_receipt,
    sample_receipt,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get("", response_model=list[PurchaseSummary])
def read_purchases(
    user: CurrentUser, db: DbSession, limit: int = Query(20, ge=1, le=100)
) -> list[PurchaseSummary]:
    """Past purchases, newest first, with total spent and items still without a price."""
    return list_purchases(db, user.household_id, limit)


@router.get("/{purchase_id}", response_model=PurchaseDetail)
def read_purchase(purchase_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PurchaseDetail:
    return purchase_detail(db, get_purchase(db, user.household_id, purchase_id))


@router.patch("/{purchase_id}/items/{item_id}", response_model=PurchaseDetail)
def update_purchase_item(
    purchase_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PurchaseItemUpdate,
    user: CurrentUser,
    db: DbSession,
) -> PurchaseDetail:
    """Fill in or fix the price paid, per product unit. It becomes the product's last price
    when this is its most recent purchase."""
    purchase = get_purchase(db, user.household_id, purchase_id)
    set_price(db, purchase, item_id, body.unit_price_cents)
    db.commit()
    return purchase_detail(db, purchase)


@router.get("/{purchase_id}/receipt/sample", response_model=ReceiptDraft)
def read_sample_receipt(purchase_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ReceiptDraft:
    """A sample receipt for what was bought, for trying the receipt flow at no cost.
    Nothing is saved until it is confirmed."""
    return sample_receipt(db, get_purchase(db, user.household_id, purchase_id))


@router.post("/{purchase_id}/receipt/read", response_model=ReceiptDraft)
def read_receipt_photo(
    purchase_id: uuid.UUID,
    body: ReceiptImage,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> ReceiptDraft:
    """Read a photo of the receipt with Claude and suggest a product for each line.

    Only for the accounts listed in RECEIPT_AI_EMAILS, never for demo households. The
    photo is sent to the model and discarded; only the confirmed prices are stored.
    """
    purchase = get_purchase(db, user.household_id, purchase_id)
    if not ai_reading_allowed(settings, user, db.get(Household, user.household_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Receipt reading is not enabled")
    try:
        size = len(base64.b64decode(body.data, validate=True))
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image data") from None
    if size > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image larger than 5 MB")
    return read_receipt(db, settings, purchase, body.media_type, body.data)


@router.put("/{purchase_id}/receipt", response_model=PurchaseDetail)
def save_receipt(
    purchase_id: uuid.UUID, body: ReceiptConfirm, user: CurrentUser, db: DbSession
) -> PurchaseDetail:
    """Save the reviewed receipt: each product's price and the total paid. Sending it
    again replaces the previous one."""
    purchase = get_purchase(db, user.household_id, purchase_id)
    confirm_receipt(db, purchase, body)
    db.commit()
    return purchase_detail(db, purchase)
