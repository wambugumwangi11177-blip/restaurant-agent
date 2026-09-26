"""Import a CSV into any record type, through the same validation, audit and
events as the API. Your CSV's column names are mapped explicitly — no bank,
M-Pesa or CRM export format is assumed.

Usage:
  python execution/import_records.py --workspace acme --type organization --csv clients.csv \\
      --map "Company=name,Sector=industry"
  python execution/import_records.py --workspace acme --type payment --csv statement.csv \\
      --map "Receipt No.=reference,Paid In=amount_minor,Completion Time=received_on" --money-major --dry-run
Options:
  --money-major  values for *_minor fields are in major units (1,500.00 -> 150000)
  --date-format  strptime format for date fields if not ISO (e.g. "%d/%m/%Y %H:%M:%S")
  --dry-run      validate every row, write nothing
Rows that fail validation are reported with their line number; valid rows are
imported (unless --dry-run). Actions are attributed to the workspace's first founder.
"""

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

import _common  # noqa: F401
from pydantic import ValidationError

from app.db import session_factory
from app.kernel import records
from app.main import bootstrap
from ingest_documents import founder_principal


def convert(field: str, value: str, money_major: bool, date_format: str | None, annotation_name: str) -> object:
    value = value.strip()
    if value == "":
        return None
    if field.endswith("_minor") and money_major:
        try:
            return int((Decimal(value.replace(",", "")) * 100).to_integral_value())
        except InvalidOperation:
            raise ValueError(f"{field}: {value!r} is not a number") from None
    if date_format and ("date" in annotation_name or field.endswith(("_on", "_date", "_at"))):
        parsed = datetime.strptime(value, date_format)
        return parsed.date().isoformat() if not field.endswith("_at") else parsed.isoformat()
    return value


def main() -> int:
    bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--type", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--map", default="", help='"CSV column=field,..." (unmapped columns with a field name are used as-is)')
    ap.add_argument("--money-major", action="store_true")
    ap.add_argument("--date-format")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rt = records.RECORD_TYPES.get(a.type)
    if rt is None:
        print(f"Unknown type {a.type!r}. Known: {', '.join(sorted(records.RECORD_TYPES))}", file=sys.stderr)
        return 2
    mapping = dict(pair.split("=", 1) for pair in a.map.split(",") if "=" in pair)
    fields = rt.create.model_fields
    db = session_factory()()
    ok = bad = 0
    try:
        principal = founder_principal(db, a.workspace)
        with open(a.csv, newline="", encoding="utf-8-sig") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                data = {}
                try:
                    for col, raw in row.items():
                        target = mapping.get(col, col)
                        if target in fields and raw is not None:
                            v = convert(target, raw, a.money_major, a.date_format, str(fields[target].annotation))
                            if v is not None:
                                data[target] = v
                    obj = rt.create.model_validate(data)
                    with db.begin_nested():
                        records.create_record(db, principal, a.type, obj)
                    ok += 1
                except (ValidationError, ValueError) as e:
                    bad += 1
                    msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()) if isinstance(e, ValidationError) else str(e)
                    print(f"line {line_no}: {msg}", file=sys.stderr)
                except Exception as e:  # noqa: BLE001 — e.g. 422 from a hook: report the row, keep going
                    bad += 1
                    print(f"line {line_no}: {getattr(e, 'detail', e)}", file=sys.stderr)
        if a.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()
    print(f"{'Would import' if a.dry_run else 'Imported'} {ok} row(s); {bad} rejected.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
