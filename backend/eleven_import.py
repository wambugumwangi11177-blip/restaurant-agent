"""Owner-only workbook import into the Eleven restaurant.

Sheets: Items, Suppliers, Recipes, Opening count. A CSV is one of those
sheets, named by the caller. Confirm is idempotent: a natural key that was
already applied is skipped and never duplicated.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

SHEETS = ("items", "suppliers", "recipes", "opening")
SHEET_TITLES = {
    "items": "Items",
    "suppliers": "Suppliers",
    "recipes": "Recipes",
    "opening": "Opening count",
}
HEADERS = {
    "items": ["item_name", "unit", "low_stock_threshold", "par_level", "cost_per_unit_kes"],
    "suppliers": ["name", "contact_phone", "contact_email", "notes"],
    "recipes": ["dish_name", "category", "ingredient_name", "quantity", "unit", "yield_fraction"],
    "opening": ["item_name", "quantity", "unit"],
}


@dataclass
class ParsedRow:
    sheet: str
    row_number: int
    values: dict
    status: str  # ok | error
    message: str = ""


@dataclass
class ParsedWorkbook:
    rows: list[ParsedRow] = field(default_factory=list)

    def errors(self) -> list[ParsedRow]:
        return [row for row in self.rows if row.status == "error"]

    def ready(self, sheet: str) -> list[ParsedRow]:
        return [row for row in self.rows if row.sheet == sheet and row.status == "ok"]


def build_template() -> bytes:
    book = Workbook()
    first = True
    for key in SHEETS:
        sheet = book.active if first else book.create_sheet()
        first = False
        sheet.title = SHEET_TITLES[key]
        sheet.append(HEADERS[key])
    notes = book.create_sheet("How to fill")
    notes.append(["sheet", "what to put"])
    notes.append(["Items", "Stock items. cost_per_unit_kes is for the owner only."])
    notes.append(["Suppliers", "Who delivers. One row per supplier name."])
    notes.append(["Recipes", "Dish, ingredient, quantity, unit, and yield (1 means nothing is lost). No prices."])
    notes.append(["Opening count", "The first counted quantity for an item that already exists or is on the Items sheet."])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value, label: str) -> tuple[float | None, str]:
    if value is None or _text(value) == "":
        return None, f"{label} is required"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{label} must be a number"
    if number != number or number in (float("inf"), float("-inf")):
        return None, f"{label} must be a real number"
    return number, ""


def _parse_sheet(sheet_key: str, header: list[str], records: list[tuple[int, list]]) -> list[ParsedRow]:
    expected = HEADERS[sheet_key]
    normalized = [_text(cell).lower() for cell in header]
    if normalized[: len(expected)] != expected:
        return [ParsedRow(sheet_key, 1, {}, "error", f"Header must be: {', '.join(expected)}")]
    parsed = []
    for row_number, cells in records:
        values = {expected[index]: cells[index] if index < len(cells) else None for index in range(len(expected))}
        if all(_text(values[column]) == "" for column in expected):
            continue
        message = ""
        cleaned: dict = {}
        if sheet_key == "items":
            name = _text(values["item_name"])
            unit = _text(values["unit"])
            if not name:
                message = "item_name is required"
            elif not unit:
                message = "unit is required"
            else:
                threshold, err = _number(values["low_stock_threshold"] if _text(values["low_stock_threshold"]) else 0, "low_stock_threshold")
                par_raw = values["par_level"]
                par = None
                if _text(par_raw):
                    par, err = _number(par_raw, "par_level")
                cost, cost_err = _number(values["cost_per_unit_kes"] if _text(values["cost_per_unit_kes"]) else 0, "cost_per_unit_kes")
                message = err or cost_err
                if not message and (threshold < 0 or cost < 0 or (par is not None and par < 0)):
                    message = "Numbers cannot be negative"
                cleaned = {
                    "item_name": name,
                    "unit": unit,
                    "low_stock_threshold": int(threshold or 0),
                    "par_level": par,
                    "cost_per_unit_kes": cost or 0,
                }
        elif sheet_key == "suppliers":
            name = _text(values["name"])
            if not name:
                message = "name is required"
            cleaned = {
                "name": name,
                "contact_phone": _text(values["contact_phone"]),
                "contact_email": _text(values["contact_email"]),
                "notes": _text(values["notes"]),
            }
        elif sheet_key == "recipes":
            dish = _text(values["dish_name"])
            ingredient = _text(values["ingredient_name"])
            unit = _text(values["unit"])
            quantity, err = _number(values["quantity"], "quantity")
            yield_raw = values["yield_fraction"]
            yield_fraction, yield_err = _number(1 if not _text(yield_raw) else yield_raw, "yield_fraction")
            message = err or yield_err
            if not dish:
                message = "dish_name is required"
            elif not ingredient:
                message = "ingredient_name is required"
            elif not unit:
                message = "unit is required"
            elif not message and (quantity is None or quantity <= 0):
                message = "quantity must be greater than 0"
            elif not message and not (0 < yield_fraction <= 1):
                message = "yield_fraction must be greater than 0 and at most 1"
            cleaned = {
                "dish_name": dish,
                "category": _text(values["category"]) or "Kitchen",
                "ingredient_name": ingredient,
                "quantity": quantity,
                "unit": unit,
                "yield_fraction": yield_fraction,
            }
        else:
            name = _text(values["item_name"])
            quantity, err = _number(values["quantity"], "quantity")
            unit = _text(values["unit"])
            message = err
            if not name:
                message = "item_name is required"
            elif not unit:
                message = "unit is required"
            elif not message and quantity < 0:
                message = "quantity cannot be negative"
            cleaned = {"item_name": name, "quantity": quantity, "unit": unit}
        parsed.append(ParsedRow(
            sheet_key,
            row_number,
            cleaned if not message else {},
            "error" if message else "ok",
            message,
        ))
    return parsed


def _title_key(title: str) -> str | None:
    cleaned = (title or "").strip().lower()
    for key, label in SHEET_TITLES.items():
        if cleaned == label.lower() or cleaned == key:
            return key
    return None


def parse_xlsx(data: bytes) -> ParsedWorkbook:
    try:
        book = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("That file is not a readable Excel workbook") from exc
    found = set()
    parsed = ParsedWorkbook()
    for sheet in book.worksheets:
        key = _title_key(sheet.title)
        if key is None:
            continue
        found.add(key)
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            parsed.rows.append(ParsedRow(key, 1, {}, "error", "Sheet is empty"))
            continue
        header = list(rows[0])
        records = [(index + 2, list(row)) for index, row in enumerate(rows[1:])]
        parsed.rows.extend(_parse_sheet(key, header, records))
    missing = [SHEET_TITLES[key] for key in SHEETS if key not in found]
    if missing:
        raise ValueError("Workbook is missing sheets: " + ", ".join(missing))
    return parsed


def parse_csv(data: bytes, sheet: str) -> ParsedWorkbook:
    import csv
    key = _title_key(sheet or "")
    if key is None:
        raise ValueError("Say which sheet this CSV is: items, suppliers, recipes, or opening.")
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty")
    parsed = ParsedWorkbook()
    parsed.rows.extend(_parse_sheet(key, rows[0], [(index + 2, row) for index, row in enumerate(rows[1:])]))
    return parsed


def _key_taken(db: Session, restaurant_id: int, sheet: str, natural_key: str) -> bool:
    return db.query(models.ImportAppliedKey).filter_by(
        restaurant_id=restaurant_id, sheet=sheet, natural_key=natural_key
    ).first() is not None


def _mark(db: Session, restaurant_id: int, sheet: str, natural_key: str) -> None:
    db.add(models.ImportAppliedKey(
        restaurant_id=restaurant_id,
        sheet=sheet,
        natural_key=natural_key,
        created_at=utcnow(),
    ))


def _find_item(db: Session, restaurant_id: int, name: str):
    return db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id,
        func.lower(models.InventoryItem.item_name) == name.lower(),
    ).first()


def _find_supplier(db: Session, restaurant_id: int, name: str):
    return db.query(models.Supplier).filter(
        models.Supplier.restaurant_id == restaurant_id,
        func.lower(models.Supplier.name) == name.lower(),
    ).first()


def _find_dish(db: Session, restaurant_id: int, name: str):
    return db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == restaurant_id,
        func.lower(models.MenuItem.name) == name.lower(),
    ).first()


def apply_import(db: Session, restaurant_id: int, user: models.User, parsed: ParsedWorkbook) -> dict:
    """Insert ready rows. Caller commits. Raises ValueError if any row is invalid."""
    if parsed.errors():
        raise ValueError("Fix the row errors before confirming")
    summary = {sheet: {"inserted": 0, "skipped": 0} for sheet in SHEETS}

    for row in parsed.ready("suppliers"):
        name = row.values["name"]
        key = name.lower()
        if _key_taken(db, restaurant_id, "suppliers", key) or _find_supplier(db, restaurant_id, name):
            if not _key_taken(db, restaurant_id, "suppliers", key):
                _mark(db, restaurant_id, "suppliers", key)
            summary["suppliers"]["skipped"] += 1
            continue
        db.add(models.Supplier(
            restaurant_id=restaurant_id,
            name=name,
            contact_phone=row.values["contact_phone"],
            contact_email=row.values["contact_email"],
            notes=row.values["notes"],
            created_at=utcnow(),
        ))
        _mark(db, restaurant_id, "suppliers", key)
        summary["suppliers"]["inserted"] += 1
    db.flush()

    for row in parsed.ready("items"):
        name = row.values["item_name"]
        key = name.lower()
        if _key_taken(db, restaurant_id, "items", key) or _find_item(db, restaurant_id, name):
            if not _key_taken(db, restaurant_id, "items", key):
                _mark(db, restaurant_id, "items", key)
            summary["items"]["skipped"] += 1
            continue
        db.add(models.InventoryItem(
            restaurant_id=restaurant_id,
            item_name=name,
            quantity=0,
            unit=row.values["unit"],
            cost_per_unit=row.values["cost_per_unit_kes"],
            low_stock_threshold=row.values["low_stock_threshold"],
            par_level=row.values["par_level"],
            expiry_days=30,
        ))
        _mark(db, restaurant_id, "items", key)
        summary["items"]["inserted"] += 1
    db.flush()

    for row in parsed.ready("opening"):
        name = row.values["item_name"]
        key = name.lower()
        item = _find_item(db, restaurant_id, name)
        if item is None:
            raise ValueError(f"Opening count row {row.row_number}: no item named {name}")
        if _key_taken(db, restaurant_id, "opening", key):
            summary["opening"]["skipped"] += 1
            continue
        item.quantity = row.values["quantity"]
        if item.unit != row.values["unit"] and not item.unit:
            item.unit = row.values["unit"]
        _mark(db, restaurant_id, "opening", key)
        summary["opening"]["inserted"] += 1

    for row in parsed.ready("recipes"):
        dish_name = row.values["dish_name"]
        ingredient_name = row.values["ingredient_name"]
        key = f"{dish_name.lower()}|{ingredient_name.lower()}"
        if _key_taken(db, restaurant_id, "recipes", key):
            summary["recipes"]["skipped"] += 1
            continue
        dish = _find_dish(db, restaurant_id, dish_name)
        if dish is None:
            dish = models.MenuItem(
                restaurant_id=restaurant_id,
                name=dish_name,
                category=row.values["category"],
                price=0,
                cost_price=0,
                description="",
                is_available=True,
            )
            db.add(dish)
            db.flush()
        ingredient = _find_item(db, restaurant_id, ingredient_name)
        if ingredient is None:
            ingredient = models.InventoryItem(
                restaurant_id=restaurant_id,
                item_name=ingredient_name,
                quantity=0,
                unit=row.values["unit"],
                cost_per_unit=0,
                low_stock_threshold=0,
                expiry_days=30,
            )
            db.add(ingredient)
            db.flush()
        existing = db.query(models.MenuIngredient).filter_by(
            menu_item_id=dish.id, inventory_item_id=ingredient.id
        ).first()
        if existing:
            _mark(db, restaurant_id, "recipes", key)
            summary["recipes"]["skipped"] += 1
            continue
        db.add(models.MenuIngredient(
            menu_item_id=dish.id,
            inventory_item_id=ingredient.id,
            quantity_per_serving=row.values["quantity"],
            is_critical=True,
            yield_fraction=row.values["yield_fraction"],
            recipe_unit=row.values["unit"],
            created_by_user_id=user.id,
            created_at=utcnow(),
        ))
        _mark(db, restaurant_id, "recipes", key)
        summary["recipes"]["inserted"] += 1

    return summary


def preview_payload(parsed: ParsedWorkbook) -> dict:
    """Owner preview. Includes the cost column because only the owner calls this."""
    sheets = {}
    for key in SHEETS:
        sheets[key] = [
            {
                "row": row.row_number,
                "status": row.status,
                "message": row.message,
                "values": row.values,
            }
            for row in parsed.rows
            if row.sheet == key
        ]
    return {
        "error_count": len(parsed.errors()),
        "ready_count": sum(1 for row in parsed.rows if row.status == "ok"),
        "sheets": sheets,
    }
