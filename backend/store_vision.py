"""Two-step check of a delivery's photos against the quantities Jack keyed.

1. OPENROUTER_VISION_MODEL (default qwen/qwen3.7-flash) reads the photos and
   returns JSON: invoice lines, and goods with a rough count or weight.
   That model is never swapped. A failed read stops the check.
2. The text model deepseek/deepseek-v4-flash compares that JSON with the keyed
   lines and writes a short plain-words note. If that call fails, qwen/qwen3.7-flash
   is tried once for the same text job and the fallback is recorded. A second
   failure is "AI check unavailable". Images are not sent to the text model.
3. The note is passed through the grounding guard. A number that is not in the
   vision JSON or the keyed lines is replaced with [unverified].

The check never blocks the delivery request: the router schedules run_check_safe.
Nothing is pushed. The note and mismatches are for the owner.
"""
import json
import logging
import re

import models
from ai.llm_client import chat_plain, chat_with_images, compare_fallback_model, compare_model, vision_model
from ai.reasoning.grounding import collect_payload_numbers, redact_free_text
from staff_audit import record_entry
from time_utils import utcnow

logger = logging.getLogger("store_vision")

_READ_PROMPT = (
    "Read the invoice photo and the goods photo. Reply with JSON only, no markdown. "
    "Use this shape: "
    '{"supplier":"","invoice_items":[{"name":"","quantity":0,"unit":""}],'
    '"goods_items":[{"name":"","quantity":0,"unit":"","weight":""}]}. '
    "quantity is a number. weight is a short note such as 'about 5 kg' when you "
    "cannot count pieces. If you cannot read a photo, use an empty list for it."
)

_COMPARE_PROMPT = (
    "You compare a photo reading with the quantities a storekeeper keyed. "
    "Reply with JSON only, no markdown. Use this shape: "
    '{{"match":true,"note":"","mismatches":[{{"item_name":"","source":"invoice","keyed":0,"seen":0}}]}}. '
    "source is invoice or goods. The note is one or two short plain sentences for the owner. "
    "Use only numbers that appear in the reading or the keyed lines. "
    "If a photo list is empty, say the photo could not be read. "
    "Reading JSON:\n{reading}\nKeyed lines JSON:\n{keyed}"
)


_HANDOVER_PROMPT = (
    "Read this photo of goods handed from a store to a kitchen. Reply with JSON only, no markdown. "
    "Use this shape: "
    '{"supplier":"","invoice_items":[],"goods_items":[{"name":"","quantity":0,"unit":"","weight":""}]}. '
    "quantity is a number. If you cannot read the photo, use an empty goods_items list."
)


def ask_model(images: list[tuple[str, bytes]], prompt: str = _READ_PROMPT) -> dict:
    """Vision step only. Raises if the reply is not a JSON object."""
    text = chat_with_images(prompt, images, model=vision_model())
    return _object(text)


def _object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("AI reply was not JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("AI reply was not an object")
    return data


def explain_difference(reading: dict, keyed: list[dict]) -> dict:
    """Text step. DeepSeek first, then Qwen once. The fallback is recorded."""
    prompt = _COMPARE_PROMPT.format(
        reading=json.dumps(reading, default=str),
        keyed=json.dumps(keyed, default=str),
    )
    parsed, used, fell_back = _complete(prompt, compare_model(), compare_fallback_model())
    note = str(parsed.get("note") or "").strip()
    grounded, ungrounded = redact_free_text(note, collect_payload_numbers({"reading": reading, "keyed": keyed}))
    mismatches = []
    for item in parsed.get("mismatches") or []:
        if not isinstance(item, dict):
            continue
        mismatches.append({
            "item_name": str(item.get("item_name") or ""),
            "source": "goods" if item.get("source") == "goods" else "invoice",
            "keyed": item.get("keyed"),
            "seen": item.get("seen"),
        })
    return {
        "note": grounded,
        "match": bool(parsed.get("match")) and not mismatches and not ungrounded,
        "mismatches": mismatches,
        "model": used,
        "fell_back": fell_back,
        "ungrounded": ungrounded,
    }


def _complete(prompt: str, primary: str, fallback: str) -> tuple[dict, str, bool]:
    """One text call, then the fallback model once. A bad reply is a failed call."""
    last = None
    models = [primary] if primary == fallback else [primary, fallback]
    for index, model in enumerate(models):
        try:
            parsed = _object(chat_plain(prompt, model=model))
            note = str(parsed.get("note") or "").strip()
            if not note:
                raise ValueError("AI note was empty")
            return parsed, model, index > 0
        except Exception as exc:
            last = exc
            logger.warning("compare model %s failed: %s", model, type(exc).__name__)
    raise last if last is not None else RuntimeError("AI check unavailable")


def _check_row(db, receipt_id: int) -> models.DeliveryVisionCheck:
    row = (
        db.query(models.DeliveryVisionCheck)
        .filter(models.DeliveryVisionCheck.receipt_id == receipt_id)
        .order_by(models.DeliveryVisionCheck.id.desc())
        .first()
    )
    if row is None:
        row = models.DeliveryVisionCheck(receipt_id=receipt_id, status="pending", created_at=utcnow())
        db.add(row)
        db.flush()
    return row


def run_check(db, receipt_id: int) -> None:
    import storage

    receipt = db.query(models.DeliveryReceipt).filter(models.DeliveryReceipt.id == receipt_id).first()
    if receipt is None:
        return
    photos = (
        db.query(models.DeliveryEvidencePhoto)
        .filter(models.DeliveryEvidencePhoto.receipt_id == receipt.id)
        .order_by(models.DeliveryEvidencePhoto.id.asc())
        .all()
    )
    lines = (
        db.query(models.DeliveryReceiptLine)
        .filter(models.DeliveryReceiptLine.receipt_id == receipt.id)
        .all()
    )
    keyed = [{"item_name": line.item_name, "quantity": line.quantity, "unit": line.unit} for line in lines]
    user = db.query(models.User).filter(models.User.id == receipt.received_by_user_id).first()
    check = _check_row(db, receipt.id)
    vision = vision_model()
    try:
        images = [(photo.content_type or "image/jpeg", storage.load(photo.storage_key)) for photo in photos]
        reading = ask_model(images)
        explained = explain_difference(reading, keyed)
        status = "mismatch" if (explained["mismatches"] or not explained["match"]) else "match"
        result = {
            "label": "AI",
            "supplier": reading.get("supplier") or "",
            "note": explained["note"],
            "mismatches": explained["mismatches"],
            "vision_model": vision,
            "compare_model": explained["model"],
            "compare_fallback": explained["fell_back"],
            "ungrounded": explained["ungrounded"],
        }
        compare_name = explained["model"]
    except Exception as exc:
        logger.warning("delivery vision check failed for receipt %s: %s", receipt_id, type(exc).__name__)
        status = "unavailable"
        result = {"label": "AI", "message": "AI check unavailable", "vision_model": vision}
        compare_name = ""
    check.status = status
    check.model_name = f"{vision} + {compare_name}".strip(" +")
    check.result_json = json.dumps(result)
    check.compared_at = utcnow()
    receipt.status = "checked"
    if user is None:
        return
    if status == "mismatch":
        names = ", ".join(item["item_name"] for item in result["mismatches"]) or "the delivery"
        fallback = " Qwen wrote the note after DeepSeek failed." if result.get("compare_fallback") else ""
        receipt.owner_review_status = "needs_approval"
        record_entry(
            db, receipt.restaurant_id, user, "delivery_ai_mismatch", "delivery_receipt",
            f"AI: {names} on delivery {receipt.id} do not match the photos.{fallback}",
            entity_id=receipt.id,
            detail={"label": "AI", "note": result["note"], "mismatches": result["mismatches"], "compare_fallback": bool(result.get("compare_fallback"))},
        )
        from routers.store_control import tell_owners
        from services.approval_workflow import ensure_reminder_row

        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == receipt.restaurant_id).first()
        if restaurant:
            tell_owners(db, user, restaurant, "Delivery needs you", f"Delivery {receipt.id} did not match the photos.")
        ensure_reminder_row(db, receipt.restaurant_id, "delivery", receipt.id, receipt.received_by_user_id)
    elif status == "unavailable":
        record_entry(
            db, receipt.restaurant_id, user, "delivery_ai_unavailable", "delivery_receipt",
            f"AI check unavailable for delivery {receipt.id}.",
            entity_id=receipt.id,
            detail={"label": "AI", "message": "AI check unavailable"},
        )
    else:
        record_entry(
            db, receipt.restaurant_id, user, "delivery_ai_match", "delivery_receipt",
            f"AI: delivery {receipt.id} matches the photos.",
            entity_id=receipt.id,
            detail={"label": "AI", "note": result["note"]},
        )


def run_handover_check(db, handover_id: int) -> None:
    """Same two models as a delivery. The handover row itself is not updated."""
    import storage

    handover = db.query(models.KitchenHandover).filter(models.KitchenHandover.id == handover_id).first()
    if handover is None or not handover.photo_storage_key:
        return
    lines = (
        db.query(models.KitchenHandoverLine)
        .filter(models.KitchenHandoverLine.handover_id == handover.id)
        .all()
    )
    keyed = [{"item_name": line.item_name, "quantity": line.quantity, "unit": line.unit} for line in lines]
    user = db.query(models.User).filter(models.User.id == handover.created_by_user_id).first()
    check = (
        db.query(models.HandoverVisionCheck)
        .filter(models.HandoverVisionCheck.handover_id == handover.id)
        .order_by(models.HandoverVisionCheck.id.desc())
        .first()
    )
    if check is None:
        check = models.HandoverVisionCheck(handover_id=handover.id, status="pending", created_at=utcnow())
        db.add(check)
        db.flush()
    vision = vision_model()
    try:
        images = [(handover.photo_content_type or "image/jpeg", storage.load(handover.photo_storage_key))]
        reading = ask_model(images, prompt=_HANDOVER_PROMPT)
        explained = explain_difference(reading, keyed)
        status = "mismatch" if (explained["mismatches"] or not explained["match"]) else "match"
        result = {
            "label": "AI",
            "note": explained["note"],
            "mismatches": explained["mismatches"],
            "vision_model": vision,
            "compare_model": explained["model"],
            "compare_fallback": explained["fell_back"],
            "ungrounded": explained["ungrounded"],
        }
        compare_name = explained["model"]
    except Exception as exc:
        logger.warning("handover vision check failed for handover %s: %s", handover_id, type(exc).__name__)
        status = "unavailable"
        result = {"label": "AI", "message": "AI check unavailable", "vision_model": vision}
        compare_name = ""
    check.status = status
    check.model_name = f"{vision} + {compare_name}".strip(" +")
    check.result_json = json.dumps(result)
    check.compared_at = utcnow()
    if user is None:
        return
    if status == "mismatch":
        names = ", ".join(item["item_name"] for item in result["mismatches"]) or "the handover"
        handover.owner_review_status = "needs_approval"
        record_entry(
            db, handover.restaurant_id, user, "handover_ai_mismatch", "kitchen_handover",
            f"AI: {names} on handover {handover.id} do not match the photo.",
            entity_id=handover.id,
            detail={"label": "AI", "note": result["note"], "mismatches": result["mismatches"]},
        )
        from routers.store_control import tell_owners
        from services.approval_workflow import ensure_reminder_row

        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == handover.restaurant_id).first()
        tell_owners(db, user, restaurant, "Handover needs you", f"Handover {handover.id} did not match the photo.")
        ensure_reminder_row(db, handover.restaurant_id, "handover", handover.id, handover.created_by_user_id)
    elif status == "unavailable":
        record_entry(
            db, handover.restaurant_id, user, "handover_ai_unavailable", "kitchen_handover",
            f"AI check unavailable for handover {handover.id}.",
            entity_id=handover.id,
            detail={"label": "AI", "message": "AI check unavailable"},
        )
    else:
        record_entry(
            db, handover.restaurant_id, user, "handover_ai_match", "kitchen_handover",
            f"AI: handover {handover.id} matches the photo.",
            entity_id=handover.id,
            detail={"label": "AI", "note": result["note"]},
        )


def run_handover_check_safe(handover_id: int) -> None:
    import database

    db = database.SessionLocal()
    try:
        run_handover_check(db, handover_id)
        db.commit()
    except Exception:
        logger.exception("handover vision task failed for handover %s", handover_id)
        db.rollback()
        try:
            check = (
                db.query(models.HandoverVisionCheck)
                .filter(models.HandoverVisionCheck.handover_id == handover_id)
                .order_by(models.HandoverVisionCheck.id.desc())
                .first()
            )
            if check is None:
                check = models.HandoverVisionCheck(handover_id=handover_id, status="unavailable", created_at=utcnow())
                db.add(check)
            check.status = "unavailable"
            check.model_name = vision_model()
            check.result_json = json.dumps({"label": "AI", "message": "AI check unavailable"})
            check.compared_at = utcnow()
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


_ZONE_STOCK_PROMPT = (
    "Read this photo of stock in a store zone. Reply with JSON only, no markdown. "
    'Use this shape: {"goods_items":[{"name":"","quantity":0,"unit":"","weight":""}]}. '
    "quantity is a number. If you cannot read the photo, use an empty goods_items list."
)


def run_zone_photo_check(db, photo_id: int) -> None:
    import storage

    photo = db.query(models.StoreZoneDayPhoto).filter(models.StoreZoneDayPhoto.id == photo_id).first()
    if photo is None:
        return
    zone = db.query(models.StockZone).filter(models.StockZone.id == photo.zone_id).first()
    balances = (
        db.query(models.StockBalance, models.InventoryItem)
        .join(models.InventoryItem, models.InventoryItem.id == models.StockBalance.inventory_item_id)
        .filter(
            models.StockBalance.restaurant_id == photo.restaurant_id,
            models.StockBalance.zone_id == photo.zone_id,
            models.StockBalance.quantity > 0,
        )
        .all()
    )
    keyed = [
        {"item_name": item.item_name, "quantity": bal.quantity, "unit": item.unit or ""}
        for bal, item in balances
    ]
    user = db.query(models.User).filter(models.User.id == photo.user_id).first()
    check = (
        db.query(models.StoreZoneDayPhotoCheck)
        .filter(models.StoreZoneDayPhotoCheck.photo_id == photo.id)
        .order_by(models.StoreZoneDayPhotoCheck.id.desc())
        .first()
    )
    if check is None:
        check = models.StoreZoneDayPhotoCheck(photo_id=photo.id, status="pending", created_at=utcnow())
        db.add(check)
        db.flush()
    vision = vision_model()
    zone_name = zone.name if zone else "the zone"
    try:
        images = [(photo.photo_content_type or "image/jpeg", storage.load(photo.photo_storage_key))]
        reading = ask_model(images, prompt=_ZONE_STOCK_PROMPT)
        explained = explain_difference(reading, keyed)
        status = "mismatch" if (explained["mismatches"] or not explained["match"]) else "match"
        result = {
            "label": "AI",
            "zone": zone_name,
            "phase": photo.phase,
            "note": explained["note"],
            "mismatches": explained["mismatches"],
            "vision_model": vision,
            "compare_model": explained["model"],
            "compare_fallback": explained["fell_back"],
            "ungrounded": explained["ungrounded"],
        }
        compare_name = explained["model"]
    except Exception as exc:
        logger.warning("zone photo check failed for photo %s: %s", photo_id, type(exc).__name__)
        status = "unavailable"
        result = {"label": "AI", "message": "AI check unavailable", "zone": zone_name, "phase": photo.phase, "vision_model": vision}
        compare_name = ""
    check.status = status
    check.model_name = f"{vision} + {compare_name}".strip(" +")
    check.result_json = json.dumps(result)
    check.compared_at = utcnow()
    if user is None:
        return
    action = f"zone_{photo.phase}_ai_{'mismatch' if status == 'mismatch' else 'match' if status == 'match' else 'unavailable'}"
    record_entry(
        db,
        photo.restaurant_id,
        user,
        action,
        "store_zone_day_photo",
        f"{zone_name} {photo.phase} photo check: {result.get('note') or result.get('message', 'done')}.",
        entity_id=photo.id,
        detail=result,
    )


def run_zone_photo_check_safe(photo_id: int) -> None:
    import database

    db = database.SessionLocal()
    try:
        run_zone_photo_check(db, photo_id)
        db.commit()
    except Exception:
        logger.exception("zone photo vision task failed for photo %s", photo_id)
        db.rollback()
    finally:
        db.close()


def run_check_safe(receipt_id: int) -> None:
    import database

    db = database.SessionLocal()
    try:
        run_check(db, receipt_id)
        db.commit()
    except Exception:
        logger.exception("delivery vision task failed for receipt %s", receipt_id)
        db.rollback()
        try:
            check = _check_row(db, receipt_id)
            check.status = "unavailable"
            check.model_name = vision_model()
            check.result_json = json.dumps({"label": "AI", "message": "AI check unavailable"})
            check.compared_at = utcnow()
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
