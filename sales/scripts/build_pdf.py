"""
Build a PDF of the restaurant leads (name, rating, phone, address), grouped by
area, from leads/kenya_restaurants.csv.

Usage:
    python sales/scripts/build_pdf.py --in leads/kenya_restaurants.csv --out leads/kenya_restaurants.pdf
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import WrapMode

NO_PHONE_SENTINEL = "N/A"


def build_rows_by_area(rows: list[dict]) -> dict[str, list[dict]]:
    by_area: dict[str, list[dict]] = {}
    for row in rows:
        by_area.setdefault(row.get("query_area", "Other"), []).append(row)
    return by_area


def sanitize(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def main():
    parser = argparse.ArgumentParser(description="Build a PDF of restaurant leads.")
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", dest="out_path", type=Path, required=True)
    parser.add_argument("--title", default="Kenya Restaurant Leads")
    args = parser.parse_args()

    with args.in_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_area = build_rows_by_area(rows)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, sanitize(f"{args.title} - {len(rows)} restaurants"), wrapmode=WrapMode.CHAR)
    pdf.ln(2)

    for area in sorted(by_area):
        area_rows = by_area[area]
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(0, 8, sanitize(f"{area} ({len(area_rows)})"), wrapmode=WrapMode.CHAR)
        pdf.set_font("Helvetica", "", 10)
        for r in area_rows:
            phone = r.get("phone") or ""
            phone = "" if phone == NO_PHONE_SENTINEL else phone
            bits = [r.get("name", "")]
            if r.get("rating"):
                bits.append(f"Rating {r['rating']}")
            if phone:
                bits.append(phone)
            if r.get("address_snippet"):
                bits.append(r["address_snippet"])
            line = "- " + " | ".join(b for b in bits if b)
            pdf.multi_cell(0, 6, sanitize(line), wrapmode=WrapMode.CHAR)
        pdf.ln(3)

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(args.out_path))
    print(f"Saved {args.out_path} ({len(rows)} restaurants, {len(by_area)} areas)")


if __name__ == "__main__":
    main()
