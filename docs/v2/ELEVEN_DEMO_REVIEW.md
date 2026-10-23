# Demo review before Eleven onboarding

The implementation plan is [ELEVEN_DEMO_PLAN.md](ELEVEN_DEMO_PLAN.md). Eleven has not been provisioned. This review uses only the separate local Demo Restaurant database.

## Walkthrough

1. Open Home and review both branches. Health tiles now show weekly money kept, sales change, stock/cash discrepancies in KES, wages and next permit expiry. Each number carries its data label. A branch with no M-Pesa statement stays incomplete.
2. Open **Team entries** in the owner header. Managers, storekeepers and controllers also have a link in their own navigation; the API enforces their roles independently of the screen.
3. Record an expense by category, amount and payment method. It enters the existing money ledger, which drives Profit & Loss. An optional receipt is private to the restaurant. Retries with the same entry key do not create a second expense.
4. Close a shift with a blind physical cash count. Times are Nairobi times, including an end after midnight. Expected cash is revealed only after submission. The count becomes available to the owner; retries do not post it twice.
5. Receive a sent purchase order. Compare ordered and received quantities before saving. Beer can be received in crates of 24; stock remains in bottles. Short receipts are recorded as partial. Attach an invoice photo and retrieve it from Recent deliveries. Large phone photos are resized before upload; the server validates and re-encodes images.
6. Open **Kitchen & money tools**. Beef stew has a sample 80% yield on both demo branches. The usable quantity was reduced proportionately, preserving the original raw stock requirement and costs. Existing recipes use yield 1 until deliberately configured.
7. Save a recipe yield, plan portions for one or more dishes, and calculate the raw prep and market list. Buying needs are prep plus full-shelf level minus stock on hand, floored at zero. This is the owner's plan, not a sales forecast or an order sent to a supplier. Recipe edits affect expectations for past sales; dish costs remain separately maintained in Menu.
8. Check a combo against saved dish costs and the owner's margin floor. No till prices change. Delivery-channel price options are explicitly distinguished from ordinary capped raises and warn that demand can fall.
9. Review the combined shift table: counted/expected cash, cash difference, M-Pesa sales and cancelled sales. Statement exceptions stay in Cash Check. M-Pesa sales are not claimed as matched receipts. Stock cannot honestly be assigned to a shift without counts bounding it, so that column says so. Overlapping drawer checks must not be added together.
10. Use the accountant export controls to download the chosen month's Excel or PDF. The existing export and monthly report use the same money engine.

## Boundaries before creating Eleven

- Identify the actual POS and confirm sales, item, payment and cancellation fields can be read. The existing MacSoft connector is not proof that a different till is supported.
- Test a real Eleven M-Pesa statement export against the parser, rather than assuming the illustrative CSV format is correct.
- Collect branch names, owner/staff roles, menu, recipes with raw/usable quantities and yield, buying units, suppliers, opening counts, bills, licences and opening finance records.
- Walk through the entry screens with the people doing the work. Browser automation was unavailable in this chat; component tests and HTTP checks do not establish real-phone usability.
- Chapter 8's learned price sensitivity, channel/daypart price lists, price ladder, long-tail menu trimming remain pending. ABC-based suggested next-count dates are now available in Planning; automatic reminders are not implemented.
- Nothing here deploys to production, changes provider credentials, sends purchasing orders, or creates Eleven's live tenant.

## Reproducing checks on Windows

`python execution/verify_eleven.py` runs the backend regression suite with remote provider keys blank. Only disposable pytest SQLite files use a memory rollback journal to avoid Windows fsync overhead; foreign keys and transaction semantics remain active. This is not a crash-durability test. Use the normal test command for durability checks.

Frontend: `npm test`, `npx tsc --noEmit`, `python execution/lint_ratchet.py`, and a production build with `NEXT_PUBLIC_API_URL=http://localhost:8000`.

Migration 057 was applied only to the local demo. A database copy passed downgrade to 056 then upgrade to 057 with all 3,225 orders preserved. PostgreSQL upgrade SQL was generated offline without contacting a database.

## Stock review added after the walkthrough

Planning now includes stock value, per-item recorded waste percentage, movement speed, suggested ABC next-count dates and same-unit supplier price history. The live demo branch has 35 stock items and 22 supplier comparisons. Values use saved unit costs, not historical FIFO valuation; negative stock and unknown costs are explicit. Waste uses recorded stock out and is not an independent physical loss measurement.
