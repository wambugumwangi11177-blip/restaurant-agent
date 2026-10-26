# Individual tool audit and completion plan — 25 October 2026

## Fixed in this correction

The reported URL contained two tool fragments, sometimes encoded as `%23`. The selection code treated that as unknown and silently rendered the complete area. Tool navigation now uses absolute paths with one `?tool=` parameter, recognises the last legacy fragment, and reports invalid tools explicitly. Every backed area block is directly discoverable. Planning uses the same selection mechanism and mounts only the selected workspace. Full overviews remain available.

Break-even already has a backend: `owner/money/breakeven.py`, composed by `areas.breakeven_summary`. Added an explicit daily target, sales, remaining amount, formula, reference month and fixed-cost breakdown. Zero current-day sales are labelled, not disguised as missing functionality.

The demand simulator was only an Ask link. Added an interactive dish/price form and owner endpoint over the same existing demand engine. The adapter carries model assumptions, suppresses contribution when ingredient cost is missing, separates dish contribution from net profit, and saves no menu price. Endpoint isolation and exact engine agreement are tested.

## Actual local API inspection

All six area endpoints respond with 31 blocks. Money has six, Sales nine, Store four, Cash five, Staff three and Setup four. The demo's M-Pesa block requires an uploaded statement; staff-on-shift requires today's schedule. These are input gaps, not invented zeroes. The remaining blocks return populated data or a specific no-findings explanation.

Planning API checks passed for catalog, shifts, stock review, menu review, saved price rules, branch comparison, forecast portions, prep calculation, combo calculation and fixed-portions P&L comparison. Calculation requests did not save prices, approve orders or send messages. Actual engine output was saved locally under `.tmp/tool-audit-*`.

## Backend work still required for full guide fidelity

1. Independent store and kitchen balances. Add a zone-aware immutable movement ledger and physical count scope, tenant-scoped opening balances, confirmed transfer pairing, independent waste records and count reconciliation. Acceptance: sending reduces store, receiving increases kitchen once; disputes preserve both declarations; a missing count cannot become a zone accusation. Backfill existing whole-item stock as unallocated, never guess a zone. Test transfer retries, partial receipt, corrections, unit/yield conversions and foreign-tenant IDs before local migration.
2. Actual provider connection. Validate client till exports/webhooks and M-Pesa statement samples, map fields, reconcile counts/totals and show source freshness. The generated demo cannot prove client-provider compatibility. Keep imports isolated and reject duplicate rows; test missing/invalid receipt IDs and statement coverage.
3. Delivery and notification evidence. The in-app alert feed and limits are accessible, but SMTP/push are unconfigured locally. Provider delivery status needs configured credentials and receipt tests before claiming external delivery. Do not enable providers just to make the demo look connected.
4. Guest win-back execution. Existing lapsed/reachable analysis is a read-only diagnostic. A campaign workflow would need consent-specific recipient review, preview, opt-out enforcement, delivery audit and explicit sending authorization; it is not represented as an already-sent campaign.

## Acceptance checklist

Every individual tool must have a unique visible heading, actual tool body or actionable missing-input reason, and its API source recorded. Browser-check canonical links, sequential selections, back/forward, reload, the exact stacked-fragment report and planning selections. Frontend tests iterate every area block independently. A successful HTTP response alone is not UI acceptance. Verification counts and screenshots are recorded in PROGRESS.md after completion.
