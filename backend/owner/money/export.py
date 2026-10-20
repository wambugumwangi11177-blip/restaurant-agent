"""
backend/owner/money/export.py — the accountant's export: one month's Profit & Loss as an XLSX workbook and a PDF
(docs/v2/SPEC.md S3.4).

Nothing is recomputed here. `month_block` asks the same shaper Home, the monthly report and `GET /owner/money/pnl` use
(areas.month_pnl → owner/money/view.py) for the month's block, plus the entries that were entered in it, and both files are
drawn from that block alone — so the workbook, the PDF and `GET /owner/report/monthly?month=…` cannot disagree.

  * the workbook holds values, not formulas: an accountant checks them against the books, and a total that is a number cannot be
    "recalculated" into something else by a spreadsheet; costs are shown as positive numbers in a cost column.
  * text that came from the books (a supplier, a note, a receipt reference) can start with = + - @ — in a spreadsheet that is a
    formula. Every such cell is stored as text and marked as text, so opening the file can never run anything.
  * text in the PDF is XML-escaped and reduced to the characters the built-in PDF fonts carry, so a supplier called
    "<b>Acme & Sons</b>" prints as written instead of breaking the page.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import models
from owner.money import categories as cats
from owner.money.pnl import pct
from owner.states import OwnerContext
from time_utils import EAT_OFFSET

PRIMARY = colors.HexColor("#275469")
GOLD = colors.HexColor("#E5B63E")
INK = colors.HexColor("#1F2A33")
MUTED = colors.HexColor("#6B7A86")
LINE = colors.HexColor("#D9D4C7")
PAPER = colors.HexColor("#F6F3EC")
GREEN = colors.HexColor("#5E9E8A")
WIDTH = A4[0] - 32 * mm

ENTRY_HEADER = ["Date", "Cost line", "Section", "Paid to", "Method", "KES", "Paid by", "Note", "Receipt"]
METHODS = {"cash": "Cash", "mpesa": "M-Pesa", "bank": "Bank", "card": "Card", "other": "Other"}
INGREDIENT_BASIS = {"recipe": "Recipe cost × dishes sold", "purchases": "What you bought in this month"}
WAGE_BASIS = {"entered": "As you entered them", "shifts": "Worked out from your shift records", "none": "Nothing recorded"}
COMMISSION_BASIS = {"entered": "As you entered them", "estimated": "Estimated from your commission rates", "none": ""}


# ── the month ────────────────────────────────────────────────────────────────

def month_block(ctx: OwnerContext, month_start: date) -> tuple[dict, list[dict]]:
    """The month's P&L block (the one the report carries) and the entries entered in it, oldest first. Voided entries are left out."""
    from owner.areas import month_pnl
    block = month_pnl(ctx, month_start)
    start, end = block["period"]["start"], block["period"]["end"]
    rows = (ctx.db.query(models.Expense).join(models.ExpenseCategory, models.ExpenseCategory.id == models.Expense.category_id)
            .filter(models.Expense.restaurant_id == ctx.rid, models.Expense.voided_at.is_(None),
                    models.Expense.paid_on >= date.fromisoformat(start), models.Expense.paid_on <= date.fromisoformat(end))
            .order_by(models.Expense.paid_on, models.Expense.id).all())
    entries = [{"date": e.paid_on, "line": e.category.name, "section": cats.PNL_LINE_NAMES.get(e.category.pnl_line, e.category.pnl_line),
                "paid_to": e.supplier or "", "method": METHODS.get(e.method, e.method), "kes": e.amount_cents / 100,
                "paid_by": e.paid_by.email if e.paid_by else "", "note": e.note or "", "receipt": e.receipt_ref or ""} for e in rows]
    return block, entries


def export_filename(restaurant_name: str, month: str, ext: str) -> str:
    """`pnl-<restaurant>-2026-09.xlsx`: letters, digits and dashes only, so it is safe in a header and on any disk."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", restaurant_name or "").strip("-").lower()[:40] or "restaurant"
    return f"pnl-{slug}-{month}.{ext}"


def _nairobi(generated_at: datetime) -> str:
    return (generated_at + EAT_OFFSET).strftime("%d %b %Y, %H:%M") + " Nairobi time"


def _share(kes: float, sales_kes: float) -> float | None:
    """`kes` as a percentage of sales, half-up to one decimal, from cents so no float arithmetic decides a rounding."""
    return pct(round(kes * 100), round(sales_kes * 100))


def _total(entries: list[dict]) -> float:
    """The entries added up in decimals, so a long list of cents cannot drift."""
    return float(sum((Decimal(str(e["kes"])) for e in entries), Decimal(0)))


def _lines(block: dict) -> dict[str, dict]:
    return {l["key"]: l for l in block["lines"]}


def _about(block: dict, restaurant_name: str, generated_at: datetime) -> list[str]:
    """The sentences that go with the figures: how they were made, what is estimated, what is missing."""
    p = block["period"]
    out = [f"{restaurant_name} — Profit & Loss — {p['label']}",
           f"Made by LEVIII on {_nairobi(generated_at)}. Amounts are in Kenya shillings (KES).",
           "",
           "How these figures were made",
           "Sales are what customers paid: paid orders that were not cancelled, counted on the Nairobi day they were taken.",
           "Costs are counted on the day they were paid (cash basis). A bill paid once a month belongs to the month it was paid in.",
           "Ingredients are the recipe cost of the dishes sold." if block["basis"]["ingredients"] == "recipe"
           else "Ingredients are what you bought in this month, because most dishes have no recipe cost yet.",
           "Voided entries are left out."]
    if block["state"] == "no_data" and block.get("reason"):
        out += ["", block["reason"]]
    if block["notes"]:
        out += ["", "Please note", *block["notes"]]
    if block["missing_categories"]:
        out += ["", "Costs you entered before and not this month: " + ", ".join(m["name"] for m in block["missing_categories"]) + "."]
    if block.get("entered_up_to"):
        out += ["", f"Costs entered up to {block['entered_up_to']}."]
    out += ["", "Targets used", *(f"{a['label']}: {a['value']:g}%" for a in block["assumptions"])]
    return out


# ── the workbook ─────────────────────────────────────────────────────────────

_MONEY = "#,##0.00"
_BOLD = Font(bold=True)
_HEAD_FILL = PatternFill("solid", fgColor="275469")
_HEAD_FONT = Font(bold=True, color="FFFFFF")
_SUB_FILL = PatternFill("solid", fgColor="F6F3EC")


def _text(cell, value) -> None:
    """Write text so a spreadsheet can never read it as a formula, whatever the first character is."""
    if value is None or value == "":
        return
    cell.value = str(value)
    cell.data_type = "s"
    if cell.value[:1] in ("=", "+", "-", "@"):
        cell.quotePrefix = True


def _header(ws, row: int, labels: list[str]) -> None:
    for i, label in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=label)
        c.font, c.fill = _HEAD_FONT, _HEAD_FILL
        c.alignment = Alignment(horizontal="right" if label in ("KES", "% of sales") else "left")


def build_xlsx(block: dict, entries: list[dict], restaurant_name: str, generated_at: datetime) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    lines = _lines(block)
    sales = lines["sales"]["kes"]
    basis = block["basis"]

    _text(ws.cell(row=1, column=1), f"{restaurant_name} — Profit & Loss — {block['period']['label']}")
    ws["A1"].font = Font(bold=True, size=14)
    _header(ws, 3, ["Line", "KES", "% of sales", "Basis"])
    row = 4

    def put(label: str, kes: float, basis_text: str = "", *, bold: bool = False, indent: int = 0, share: float | None | bool = True, fill=None):
        nonlocal row
        a = ws.cell(row=row, column=1)
        _text(a, label)
        a.alignment = Alignment(indent=indent)
        b = ws.cell(row=row, column=2, value=kes)
        b.number_format = _MONEY
        c = ws.cell(row=row, column=3, value=_share(kes, sales) if share is True else share)
        c.number_format = "0.0"
        _text(ws.cell(row=row, column=4), basis_text)
        for cell in (a, b, c, ws.cell(row=row, column=4)):
            if bold:
                cell.font = _BOLD
            if fill:
                cell.fill = fill
        row += 1

    put("Sales", sales, "Paid orders, by the day taken", bold=True, share=100.0 if sales else None)
    put("Ingredients", -lines["ingredients"]["kes"], INGREDIENT_BASIS[basis["ingredients"]])
    put("Left after ingredients", lines["left_after_ingredients"]["kes"], "Sales minus ingredients", bold=True, fill=_SUB_FILL)
    put("Wages", -lines["wages"]["kes"], WAGE_BASIS[basis["wages"]])
    put("Other costs", -lines["other_costs"]["kes"], "Everything below, as you entered it" if block["sections"] else "Nothing entered", bold=True)
    for sec in block["sections"]:
        put(sec["name"], sec["kes"], "", bold=True, indent=1)
        for line in sec["lines"]:
            how = COMMISSION_BASIS[line["basis"]] if line.get("basis") else (f"{line['entries']} entr{'y' if line['entries'] == 1 else 'ies'}" if line["entries"] else "")
            put(line["name"], line["kes"], how + (" · fixed" if line["is_fixed"] and how else ""), indent=2)
    put("What you kept", lines["kept"]["kes"], "Left after ingredients, minus wages and other costs", bold=True, fill=_SUB_FILL)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 36, 16
    ws.column_dimensions["C"].width, ws.column_dimensions["D"].width = 12, 52
    ws.freeze_panes = "A4"

    es = wb.create_sheet("Entries")
    _header(es, 1, ENTRY_HEADER)
    for r, e in enumerate(entries, 2):
        d = es.cell(row=r, column=1, value=e["date"])
        d.number_format = "yyyy-mm-dd"
        for col, key in ((2, "line"), (3, "section"), (4, "paid_to"), (5, "method"), (7, "paid_by"), (8, "note"), (9, "receipt")):
            _text(es.cell(row=r, column=col), e[key])
        k = es.cell(row=r, column=6, value=e["kes"])
        k.number_format = _MONEY
    total_row = len(entries) + 2
    _text(es.cell(row=total_row, column=1), "Total entered")
    total = es.cell(row=total_row, column=6, value=_total(entries))
    total.number_format = _MONEY
    for col in range(1, len(ENTRY_HEADER) + 1):
        es.cell(row=total_row, column=col).font = _BOLD
        es.column_dimensions[get_column_letter(col)].width = (12, 26, 18, 24, 10, 14, 26, 36, 22)[col - 1]
    es.freeze_panes = "A2"

    ab = wb.create_sheet("About")
    for r, text in enumerate(_about(block, restaurant_name, generated_at), 1):
        c = ab.cell(row=r, column=1)
        _text(c, text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if text and (r == 1 or text in ("How these figures were made", "Please note", "Targets used")):
            c.font = _BOLD
    ab.column_dimensions["A"].width = 110

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── the PDF ──────────────────────────────────────────────────────────────────

def clean(text) -> str:
    """The built-in PDF fonts carry Latin-1/cp1252; anything else is replaced rather than crashing the document."""
    text = str(text).replace("→", "->").replace("≤", "<=").replace("≥", ">=")
    return text.encode("cp1252", "replace").decode("cp1252")


def esc(text) -> str:
    return escape(clean(text))


def kes_text(v: float) -> str:
    """"KES 412,000"; shillings and cents only when there are cents; a loss as "-KES 1,200"."""
    whole = abs(v) == round(abs(v))
    body = f"{abs(v):,.0f}" if whole else f"{abs(v):,.2f}"
    return f"{'-' if v < 0 else ''}KES {body}"


def _pct_text(v: float | None) -> str:
    return "" if v is None else f"{v:.1f}%"


STYLES = {
    "eyebrow": ParagraphStyle("eyebrow", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=10, spaceAfter=2),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, textColor=INK, leading=28, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, textColor=MUTED, leading=13),
    "lead": ParagraphStyle("lead", fontName="Helvetica", fontSize=12, textColor=INK, leading=17, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, textColor=PRIMARY, leading=16, spaceBefore=12, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=13.5),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK, leading=11),
    "cellr": ParagraphStyle("cellr", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11, alignment=TA_RIGHT),
    "cellbr": ParagraphStyle("cellbr", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK, leading=11, alignment=TA_RIGHT),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
    "thr": ParagraphStyle("thr", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10, alignment=TA_RIGHT),
    "note": ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8, textColor=MUTED, leading=11),
}


def P(text, style="body") -> Paragraph:
    return Paragraph(esc(text), STYLES[style])


def _table(rows, widths, bold_rows=()) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
             ("BACKGROUND", (0, 0), (-1, 0), PRIMARY)]
    style += [("BACKGROUND", (0, r), (-1, r), PAPER) for r in bold_rows]
    t.setStyle(TableStyle(style))
    return t


def _bar(shares: list[tuple[str, float, colors.Color]]) -> Drawing:
    """The four shares of every KES 100 as one bar, in the order the money leaves: ingredients, wages, other costs, what you kept."""
    d = Drawing(WIDTH, 34)
    total = sum(max(v, 0) for _l, v, _c in shares) or 1
    x = 0.0
    for label, v, colour in shares:
        w = WIDTH * max(v, 0) / total
        if w:
            d.add(Rect(x, 14, w, 16, fillColor=colour, strokeColor=colors.white, strokeWidth=1))
            if w > 38:
                d.add(String(x + 4, 19, f"{v:.1f}", fontName="Helvetica-Bold", fontSize=8, fillColor=colors.white))
        x += w
    x = 0.0
    for label, v, _c in shares:
        w = WIDTH * max(v, 0) / total
        if w > 38:
            d.add(String(x + 4, 3, clean(label), fontName="Helvetica", fontSize=7, fillColor=MUTED))
        x += w
    return d


def build_pdf(block: dict, entries: list[dict], restaurant_name: str, generated_at: datetime, *, compress: bool = True) -> bytes:
    lines = _lines(block)
    p, share = block["period"], block["out_of_every_100"]
    sales, kept = lines["sales"]["kes"], lines["kept"]["kes"]
    title = f"{restaurant_name} Profit & Loss {p['label']}"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 10 * mm, clean(f"Made by LEVIII on {_nairobi(generated_at)}. Costs are counted on the day they were paid."))
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(LINE)
        canvas.line(16 * mm, 14 * mm, A4[0] - 16 * mm, 14 * mm)
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=20 * mm,
                            title=clean(title), author=clean(restaurant_name), pageCompression=1 if compress else 0, invariant=not compress)
    verb = "kept" if kept >= 0 else "lost"
    story = [P(f"{restaurant_name.upper()}  |  PROFIT & LOSS", "eyebrow"), P("Profit & Loss", "title"), P(p["label"], "sub"),
             P(f"You sold {kes_text(sales)} and {verb} {kes_text(abs(kept))}." if sales or kept else "Nothing is recorded for this month.", "lead")]

    if block["sales_split"] and sales:
        s = block["sales_split"]
        story.append(P(f"Food {kes_text(s['food'])}  |  Drinks {kes_text(s['drinks'])}  |  Other {kes_text(s['other'])}", "note"))

    if sales:
        story += [P("Out of every KES 100 you took", "h2"),
                  _bar([("Ingredients", share["ingredients"] or 0, PRIMARY), ("Wages", share["wages"] or 0, GOLD),
                        ("Other costs", share["other_costs"] or 0, MUTED), ("What you kept", max(share["kept"] or 0, 0), GREEN)])]

    rows = [[P("Line", "th"), P("KES", "thr"), P("% of sales", "thr")]]
    bold: list[int] = []

    def add(label, kes, *, strong=False, indent=0, with_share=True):
        if strong:
            bold.append(len(rows))
        rows.append([Paragraph(("&nbsp;" * 4 * indent) + esc(label), STYLES["cellb" if strong else "cell"]), P(kes_text(kes), "cellbr" if strong else "cellr"),
                     P(_pct_text(_share(kes, sales)) if with_share and sales else "", "cellbr" if strong else "cellr")])

    add("Sales", sales, strong=True)
    add("Ingredients", -lines["ingredients"]["kes"])
    add("Left after ingredients", lines["left_after_ingredients"]["kes"], strong=True)
    add("Wages", -lines["wages"]["kes"])
    add("Other costs", -lines["other_costs"]["kes"], strong=True)
    for sec in block["sections"]:
        add(sec["name"], sec["kes"], indent=1)
        for line in sec["lines"]:
            add(line["name"] + (" (estimated)" if line.get("basis") == "estimated" else ""), line["kes"], indent=2)
    add("What you kept", kept, strong=True)
    story += [P("The month, line by line", "h2"), _table(rows, [WIDTH * 0.6, WIDTH * 0.22, WIDTH * 0.18], bold)]

    notes = [n for n in block["notes"]] + ([block["reason"]] if block["state"] == "no_data" and block.get("reason") else [])
    if notes:
        story += [Spacer(1, 6), KeepTogether([P("Please note", "h2"), *[P(n, "body") for n in notes]])]

    if entries:
        erows = [[P("Date", "th"), P("Cost line", "th"), P("Paid to", "th"), P("KES", "thr")]]
        for e in entries:
            who = e["paid_to"] + (f" — {e['note']}" if e["note"] and e["paid_to"] else e["note"])
            erows.append([P(e["date"].isoformat(), "cell"), P(e["line"], "cell"), P(who, "cell"), P(kes_text(e["kes"]), "cellr")])
        erows.append([P("Total entered", "cellb"), P("", "cell"), P("", "cell"), P(kes_text(_total(entries)), "cellbr")])
        story += [P("What was entered this month", "h2"), _table(erows, [WIDTH * f for f in (0.14, 0.26, 0.42, 0.18)], [len(erows) - 1])]

    story += [Spacer(1, 8), P("Targets used: " + "; ".join(f"{a['label']} {a['value']:g}%" for a in block["assumptions"]) + ".", "note")]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
