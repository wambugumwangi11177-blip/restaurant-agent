# LEVIII owner mockups — notes

## Page list

- index.html (developer index)
- home.html
- money.html
- stock.html
- ask.html
- more.html
- sales-dishes.html
- cash-check.html
- staff.html
- settings.html
- reports.html
- alerts.html

## How data flows

Read-only alignment with the live backend (no `docs/v2/` folder in this repo; owner experience is documented in `directives/016_*`, `directives/015_*`, and ADRs 0005/0007).

**Who sees what:** Eleven’s owner uses these mockups on a phone. Staff in the real app include **Manager**, **Storekeeper (Jack)**, **Kitchen**, and **Accountant**; the owner sees outcomes (counts, transfers, shift closes), not staff UI. A storekeeper send that does not match a kitchen blind count surfaces as **Handover doesn't match** (backend: `StockTransfer` PENDING → CONFIRMED or **DISPUTED** via `POST /stock/transfers` and `POST /stock/transfers/{id}/confirm` in `routers/stock_custody.py`).

**Sales (automatic):** Paid orders land from the restaurant **POS/till (Quick Sell at Eleven)** through a **MacSoft webhook push** into LEVIII’s mirror (`routers/webhooks.py` → `integration/ingest.py`). Home sales and freshness copy mirror **`GET /api/v1/overview/today`**: `revenue` (paid, non-cancelled orders by creation time), `data_provenance.latest_order_at`, and `source_connection.state` (direct vs receiving vs awaiting_first_delivery). Mockup line: *“Your till updated 2 minutes ago”*.

**Staff-entered data:** Deliveries and purchase orders (storekeeper), **store→kitchen transfers** and kitchen confirms, spoilage/write-offs, **cash drawer counts** (`POST /cash-reconciliation/counts`), bills/licences, and recipes/costs. Freshness lines call out lag (*costs entered up to Tuesday*, *not updated since Monday*).

**Deterministic vs AI:** All **numbers** in `assets/sample-data.js` stand in for deterministic engines (overview attention cards, profit/menu/pricing intelligence, `ai/stock_custody.py` variance, `ai/cash_reconciliation.py`, etc.). The **LLM never computes figures** (ADR 0005). AI-only copy is labelled **Written by AI**: Home “LEVIII’s read”, Ask answers’ narrative sentences, Reports “My read / Try this”, and promotional wording. **Why?** sheets describe the deterministic calculation path, not AI guesswork.

**Navigation vs API:** The PDF’s five tabs map to area pages; the shipped home feed is **`/api/v1/overview/today`** (`attention`, `pulse`, `revenue`, `stock`, `staff`, `performance`) rather than a separate `/owner/home` route in this codebase. Mockup filenames follow the PDF file map.

## Assumptions

- Profile circle links to Settings (Permits & Settings live there per sprint 8).
- Branch A / B food cost percentages are in sample-data.js for future use; not shown on every page yet.
- Report tab "This year" shows Jan–Oct bars with Nov–Dec as zero placeholders until year ends.
- Tue Night shift is the only row marked Check on Cash Check, per sprint 5.
- Delivery and card payment split uses month totals on Money page regardless of Today/Week toggle (toggle updates P&L hero and list only).
- Eleven’s POS is Quick Sell; ingest path follows the MacSoft mirror pattern until a dedicated Quick Sell slug appears in code.

## Unfinished

- None identified after Sprint 9 review.
