"""Downloadable owner report for the Demo Restaurant.

Renders the dictionary produced by ``demo_scenario.report`` as a short, plain-language
PDF with charts. It reads that dictionary only: no database access, no new figures, so the
PDF, the Reports page and the OS answers can never disagree.
"""
import math
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor("#275469")
GOLD = colors.HexColor("#E5B63E")
INK = colors.HexColor("#1F2A33")
MUTED = colors.HexColor("#6B7A86")
LINE = colors.HexColor("#D9D4C7")
PAPER = colors.HexColor("#F6F3EC")
PALETTE = [PRIMARY, GOLD, colors.HexColor("#5E9E8A"), colors.HexColor("#B5651D"), colors.HexColor("#8E7CC3"), colors.HexColor("#9AA5AE")]
WIDTH = A4[0] - 32 * mm


def clean(text):
    """Base-14 PDF fonts cover Latin-1/cp1252; anything else is replaced rather than crashing."""
    text = str(text).replace("→", "->").replace("≤", "<=").replace("≥", ">=")
    return text.encode("cp1252", "replace").decode("cp1252")


def esc(text):
    return escape(clean(text))


def money(v):
    return f"KES {round(v):,}"


STYLES = {
    "eyebrow": ParagraphStyle("eyebrow", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=10, spaceAfter=2),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, textColor=INK, leading=28, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, textColor=MUTED, leading=13),
    "lead": ParagraphStyle("lead", fontName="Helvetica", fontSize=12, textColor=INK, leading=17, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, textColor=PRIMARY, leading=16, spaceBefore=12, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=13.5),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK, leading=11),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
    "note": ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8, textColor=MUTED, leading=11),
    "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=10),
    "kpi_value": ParagraphStyle("kpi_value", fontName="Helvetica-Bold", fontSize=15, textColor=INK, leading=19),
}


def P(text, style="body"):
    return Paragraph(esc(text), STYLES[style])


def line_chart(series, width, height=150):
    d = Drawing(width, height)
    lc = HorizontalLineChart()
    lc.x, lc.y, lc.width, lc.height = 42, 24, width - 58, height - 38
    lc.data = [[r["revenue"] for r in series]]
    step = max(1, math.ceil(len(series) / 8))
    lc.categoryAxis.categoryNames = [
        (r["day"] if len(series) <= 8 else r["date"][5:]) if i % step == 0 else "" for i, r in enumerate(series)]
    lc.categoryAxis.labels.fontSize = 7
    lc.categoryAxis.labels.fillColor = MUTED
    lc.categoryAxis.strokeColor = LINE
    lc.valueAxis.valueMin = 0
    lc.valueAxis.labels.fontSize = 7
    lc.valueAxis.labels.fillColor = MUTED
    lc.valueAxis.labelTextFormat = lambda v: f"{v / 1000:.0f}k"
    lc.valueAxis.strokeColor = LINE
    lc.valueAxis.gridStrokeColor = LINE
    lc.valueAxis.visibleGrid = True
    lc.lines[0].strokeColor = PRIMARY
    lc.lines[0].strokeWidth = 2
    lc.lines[0].symbol = makeMarker("FilledCircle")
    lc.lines[0].symbol.fillColor = PRIMARY
    lc.lines[0].symbol.size = 4
    d.add(lc)
    return d


def bar_chart(pattern, width, height=130):
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 36, 22, width - 46, height - 34
    bc.data = [[r["revenue"] for r in pattern]]
    bc.categoryAxis.categoryNames = [r["day"] for r in pattern]
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fillColor = MUTED
    bc.valueAxis.valueMin = 0
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fillColor = MUTED
    bc.valueAxis.labelTextFormat = lambda v: f"{v / 1000:.0f}k"
    bc.valueAxis.gridStrokeColor = LINE
    bc.valueAxis.visibleGrid = True
    bc.bars[0].fillColor = PRIMARY
    bc.bars[0].strokeColor = None
    bc.barWidth = 12
    peak = max(range(len(pattern)), key=lambda i: pattern[i]["revenue"])
    bc.bars[(0, peak)].fillColor = GOLD
    d.add(bc)
    return d


def donut(items, width, height=130):
    d = Drawing(width, height)
    total = sum(i["value"] for i in items) or 1
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 6, 12, height - 24, height - 24
    pie.data = [i["value"] for i in items]
    pie.labels = None
    pie.innerRadiusFraction = 0.55
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 1
    for idx in range(len(items)):
        pie.slices[idx].fillColor = PALETTE[idx % len(PALETTE)]
    d.add(pie)
    legend = Legend()
    legend.x, legend.y = height, height - 30
    legend.fontName, legend.fontSize = "Helvetica", 8
    legend.alignment = "right"
    legend.dy = legend.dx = 7
    legend.deltay = 12
    legend.colorNamePairs = [(PALETTE[i % len(PALETTE)], clean(f"{it['label']} ({round(it['value'] / total * 100)}%)")) for i, it in enumerate(items)]
    d.add(legend)
    return d


def table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), PRIMARY)]
    if zebra:
        style += [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, PAPER])]
    t.setStyle(TableStyle(style))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 10 * mm, clean("Illustrative sample data. Calculated from a demonstration scenario, not actual restaurant results."))
    canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 14 * mm, A4[0] - 16 * mm, 14 * mm)
    canvas.restoreState()


def build_pdf(report, restaurant_name="Demo Restaurant"):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=20 * mm,
                            title=clean(f"{restaurant_name} {report['period']} report"), author=clean(restaurant_name))
    story = [P(f"{restaurant_name.upper()}  |  OWNER REPORT", "eyebrow"),
             P(f"{report['period'].capitalize()} report", "title"),
             P(f"{report['range']}  |  {report['coverage_days']} sample day{'s' if report['coverage_days'] != 1 else ''}", "sub"),
             P(report["headline"], "lead")]

    kpi = Table([[P(k["label"], "kpi_label") for k in report["kpis"]], [P(k["value"], "kpi_value") for k in report["kpis"]]],
                colWidths=[WIDTH / len(report["kpis"])] * len(report["kpis"]))
    kpi.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                             ("LINEAFTER", (0, 0), (-2, -1), 0.4, LINE)]))
    story += [kpi, Spacer(1, 4)]
    comp = report.get("comparison")
    if comp:
        word = "up" if comp["change_pct"] >= 0 else "down"
        story.append(P(f"Sales are {word} {abs(comp['change_pct'])}% compared with {comp['label']} ({money(comp['previous_revenue'])}).", "note"))

    story += [P("How sales moved", "h2"),
              P("The line follows sales day by day. A rising line means the restaurant is earning more; a dip is a quieter day worth understanding.", "note"),
              Spacer(1, 4), line_chart(report["series"], WIDTH)]

    left = [P("Which days are busiest", "h2"), P("Average sales by weekday over the sample history. The gold bar is your busiest day.", "note"), bar_chart(report["weekday_pattern"], WIDTH / 2 - 8)]
    right = [P("Where orders came from", "h2"), P("How guests ordered today.", "note"), donut(report["channels"], WIDTH / 2 - 8)]
    pair = Table([[left, right]], colWidths=[WIDTH / 2, WIDTH / 2])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story += [Spacer(1, 4), pair]

    story.append(P("The story in plain words", "h2"))
    for part in report["story"]:
        story.append(KeepTogether([Paragraph(f"<b>{esc(part['title'])}.</b> {esc(part['text'])}", STYLES["body"]), Spacer(1, 5)]))

    money_today = report.get("money_today")
    if money_today:
        rows = [[P("Where today's money went", "th"), P("Amount", "th")],
                [P("Sales", "cell"), P(money(money_today["sales"]), "cell")],
                [P("Ingredients", "cell"), P(money(money_today["food_cost"]), "cell")],
                [P("Staff", "cell"), P(money(money_today["labor"]), "cell")],
                [P("Other running costs", "cell"), P(money(money_today["other"]), "cell")],
                [P("What is left", "cellb"), P(money(money_today["surplus"]), "cellb")]]
        story += [KeepTogether([P("Where the money went", "h2"), table(rows, [WIDTH * 0.6, WIDTH * 0.4]),
                                P("Contribution (sales minus ingredients) is not profit; staff and running costs still come out of it.", "note")])]

    if report.get("dishes"):
        rows = [[P(h, "th") for h in ("Dish", "Price", "Sold today", "Sales", "Kept per plate")]]
        for d in report["dishes"]:
            rows.append([P(d["name"], "cellb"), P(money(d["price"]), "cell"), P(str(d["units"]), "cell"), P(money(d["sales"]), "cell"),
                         P(f"{money(d['price'] - d['cost'])} ({d['margin_pct']}%)", "cell")])
        story += [KeepTogether([P("Your menu today", "h2"), table(rows, [WIDTH * f for f in (0.28, 0.16, 0.16, 0.18, 0.22)]),
                                P("'Kept per plate' is the price minus the cost of ingredients.", "note")])]

    if report.get("decisions"):
        rows = [[P(h, "th") for h in ("Idea", "Why", "Next step", "Possible value")]]
        for d in report["decisions"]:
            rows.append([P(d["idea"], "cellb"), P(d["why"], "cell"), P(d["next_step"], "cell"), P(d["expected"] or "-", "cell")])
        story += [KeepTogether([P("What we suggest", "h2"), table(rows, [WIDTH * f for f in (0.24, 0.32, 0.26, 0.18)]),
                                P("These are chances, not results. Nothing has been changed and nothing has been earned yet.", "note")])]

    if report.get("note"):
        story += [Spacer(1, 6), P(report["note"], "note")]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
