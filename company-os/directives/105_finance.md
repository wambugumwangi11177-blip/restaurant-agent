# Directive 105 — Finance (founder only)

**Hard rule: the OS never moves money.** No tool pays, transfers or refunds, and a test asserts it (`test_finance_is_founder_only_and_never_moves_money`). Finance records, reconciles, reminds and reports.

**Records:**
- invoice: auto-numbered `INV-YYYY-NNNN`; total = subtotal + tax; status follows its payments.
- payment: mpesa, bank, cash, card or other, with a reference; recalculates its invoice.
- expense: can't be confirmed without a category.
- subscription.
- cash_snapshot: balance per account on a date.

**What is deliberately NOT built in** (confirm each with your accountant):
- **Tax:** no VAT rate, threshold or rule. `tax_minor` is entered per invoice.
- **eTIMS:** `etims_reference` stores the invoice number your eTIMS system issues. The OS does not connect to KRA.
- **M-Pesa statements:** no statement format is assumed. Import with `execution/import_records.py --type payment --money-major --date-format "…" --map "<your columns>=reference,amount_minor,received_on"`.
- **FX:** no exchange rates. Reports total per currency, and runway counts only the workspace currency, stating what it excluded.

**Agents** (all deterministic)
| Agent | On its own | Needs approval |
|---|---|---|
| bookkeeper | set `suggested_category` from your own confirmed history for the same vendor | confirming is always yours |
| collections | draft reminders for overdue invoices to a person linked to the client organization | every reminder (email proposal) |
| runway_reporter | cash ÷ average net burn over the last 3 complete months | — |

**Job:** `collections_check` (daily) notifies founders of invoices that have become overdue.

**Reports:**
- finance.receivables
- finance.month (parameter `month`=YYYY-MM; confirmed expenses only)
- finance.runway
- finance.unmatched (exact-amount match candidates; you decide the match)

**Done gate:** one full month closed in the OS that matches your bank and M-Pesa statements to the shilling. Status: ⏳ open. It needs your real statements, and your accountant's confirmation of the tax items above.
