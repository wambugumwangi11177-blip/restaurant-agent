# Eleven connected day — evidence and remaining gaps

Implementation: `codex/eleven-demo-readiness`, 25 October 2026. Matrix: [ELEVEN_DAILY_MATRIX.md](ELEVEN_DAILY_MATRIX.md). The existing working tree and operational demo dataset were preserved. No production tenant, deployment, supplier approval or external message is part of this work.

## Reproducible checks

The Windows runner `execution/verify_eleven.py` points pytest at disposable databases and disables synchronous disk writes **only** for pytest temporary SQLite files. It does not alter durability settings on the running local demo. Provider clients in the test runner are blank/stubbed. The migration copy tests and actual local runtime use their own explicit file paths.

| Evidence | Result | Local record |
|---|---|---|
| Daily records, PDF-visible features, existing Eleven workflows, Money, custody/roles, recipe deduction, Ask forms, financial goldens, tenant isolation and identity | 229 passed | `.tmp/eleven-daily-final-backend-all.log` |
| Same-day delivery through close, followed by correction; unified aliases, totals, report and PDF contracts | 10 passed | `.tmp/eleven-daily-report-recheck.log` |
| Latest role/location, branch isolation, late Nairobi count, closure correction, shared reports and PIN regression | 62 passed | `.tmp/eleven-daily-role-final.log` |
| Existing personal PIN opt-in, verification, lockout and tenant guards | 7 passed | `.tmp/eleven-daily-pin-checks.log` |
| Earlier entire frontend suite after task/filter/error-state changes | 301 passed, 26 files | `.tmp/eleven-daily-verified-frontend.log` |
| Final frontend including staff location pages | 302 checks covered: 271 passed in the 24-file run; 31 passed on the two worker-startup retries | `.tmp/eleven-daily-final-all-ui.log`, `.tmp/eleven-daily-worker-rechecks.log` |
| Latest conversations, quantities, locations, closure, offline and Nairobi boundaries | 125 passed; subsequent offline/undo recheck 37 passed | `.tmp/eleven-daily-final-conversations.log`, `.tmp/eleven-daily-offline-final.log` |
| Read-only running API checks using owner and four staff identities on both branches | 77 checks/identity proofs passed | `.tmp/eleven-daily-live-evidence.json`, `.tmp/eleven-daily-live.log` |
| Actual local PIN switch, waiter → chef | New token identifies the chef personally and retains Kasarani branch 2; roster identifies branch | `.tmp/eleven-daily-live-pin.json` |
| Migration 059 | Local demo upgraded; copied DB downgrade/upgrade and offline PostgreSQL DDL checked | `.tmp/eleven-059-roundtrip.log`, `.tmp/eleven-059-postgres.sql` |
| Existing orders | 3,225 before and after; original backup remains at revision 058 | `backend/local_latest_owner.db`, `.tmp/eleven-before-059.db` |

These test groups overlap and must not be added as unique test counts. Baseline FastAPI/Pydantic deprecation messages and jsdom's unsupported full-navigation stderr remain. Worker startup also timed out on two files after dependency relocation; both files passed when rerun (31 checks). The final 302-check coverage is therefore across that run and its targeted retries, not a claim that the last full invocation had no runner errors. Earlier failing logs are retained rather than relabelled as passing.

Final production-build and lint results are recorded in PROGRESS.md and `.tmp/eleven-daily-verified-build.log` / `.tmp/eleven-daily-verified-lint.log`. The existing lint baseline is 14 errors and four warnings; the ratchet checks that this change adds none.

## Scenario ledger

`backend/tests/test_eleven_daily.py` drives the same HTTP services used by the application, with a real disposable relational database. The shared recipe service is called at the sale lifecycle boundary.

| Scenario | Assertions |
|---|---|
| Complete clean restaurant day | Receive 10 kg once, dispatch 4 kg, independent chef confirms 4 kg, two recipe portions consume 1 kg once, record 0.2 kg spoilage. Store 6 + kitchen 2.8 = global 8.8 kg; unallocated and transit zero. Preserve one expiry batch. Whole-item count, assigned waiter's blind KES 1,000 cash count, accountant review, owner clean close. Home and daily report both show KES 1,000 sales and the report shows the closed state. |
| Correction after that close | Append a physical count correction to 9 kg. Original close and original records remain in history; review reopens. |
| Short kitchen receipt | Accountant dispatches 4 kg; chef independently reports 3.8 kg. Disputed state retained, 0.2 kg stays in transit, no fabricated whole-stock receipt, retry creates no extra arrival events. |
| Self-confirmation | HTTP sender confirmation fails; the shared service used by HTTP and WhatsApp contains the same actor check. |
| Simultaneous confirmations | Two independent database sessions race. One confirmation result and one movement pair remain, with exactly two arrival events. |
| Spoilage and locating historical stock | First store count assigns existing unallocated quantity before changing total stock. Structured waste decreases the correct location and global stock once. Original reason, actor and capture time retained. |
| Missing required records | A clean close returns 409. Accountant cannot override missing evidence; owner can explicitly close with an audited exception. |
| Cash discrepancy | Existing cash/shift tests preserve expected/count/gap, configured tolerance and statement/stock attribution limits. Blind submission never returns expected cash to the waiter. |
| Offline/stale record | A count captured before a later global or location-only movement is rejected. Existing branch-bound offline entry queues and retry journals remain. Yesterday's unsubmitted drawer assignment stays visible after midnight. |
| Incomplete M-Pesa | Incomplete coverage or unmatched statement receipts cannot become a clean close, including a receipt without a recorded sale. |
| Isolation, missing inputs and unknown expiry | Foreign branch items/photos fail; staff cannot read owner reports; absent costs remain unknown; absent expiry remains unknown; historic stock is not assigned a guessed location. |

## Browser evidence and its limit

### Final follow-through — 26 October 2026

The previously missing phone/desktop pass is now complete for the listed primary owner and staff surfaces. **72 route visits** at 390 and 1440 px passed without horizontal overflow or JavaScript exceptions. **Four interaction journeys** verified report-period reload/Back, review-date reload, and menu/PIN-roster recovery after controlled HTTP 503 responses. **Eight additional journeys** proved waiter sales, stockkeeper/accountant location records and chef kitchen-arrival confirmation are each reachable in one navigation action from the relevant landing page. This does not claim every optional legacy administration screen was visually reviewed.

Reproducible scripts: `.tmp/resume-browser.cjs` and `.tmp/resume-navigation.cjs`. Structured results and screenshots: `.tmp/resume-browser/` (`results.json`, `navigation.json`). The 303-test frontend suite, production build, TypeScript and lint ratchet passed. Lint retains its existing 14 errors/four warnings with no regression. Authenticated read-only API checks passed 91 checks/identity proofs across both branches. The daily/financial recheck passed 56 tests after correcting a midnight-sensitive golden fixture and a stale test-session object. The broader overlapping run covered 93 tests; its remaining exact-midnight fixture case was corrected and included in that final recheck. No live demo records were reseeded or altered by these validation scripts.

The verified frontend runtime is `D:/codex-eleven-runtime/2026-10-26-frontend`; workspace `frontend/node_modules` and `.next` link there. `.tmp` and `docs/v2` also retain their original paths through junctions to D: after repeated system-drive exhaustion. Original dependency/build copies and a recovered progress-log backup are retained. The backend continues to use the existing explicit local SQLite database. Both servers run on their documented local ports. D: must remain available for this local arrangement.

The following paragraphs preserve the earlier interrupted-run record; their outstanding final-browser gap is superseded by this entry.

Browser control visually inspected the compact owner Home at desktop width and the waiter's new daily landing. The waiter reached the manual POS in one navigation action. Earlier individual-tool browser work separately checked all six areas, unique tool bodies, legacy fragments, Back and planning selections; see `PROGRESS.md` and the earlier `.tmp/tool-browser-audit.json` evidence.

The final all-screen phone/desktop walkthrough is **not complete**. Browser control became unavailable while this turn was running; the final retry/error, period-filter and planning-chooser refinements were verified by frontend tests and build rather than a new browser pass. No final screenshots are presented as if they had been captured. This remains an explicit acceptance gap, not an HTTP-200 substitute for usability acceptance.

## Local access and runtime

- App: `http://localhost:3000/home`; API: `http://127.0.0.1:8000`.
- Owner restaurant sign-in: `Demo Restaurant`, existing local password `LocalDemo2026!`.
- Local staff sign-in uses **Sign in with email instead**. Emails are `eleven-1-{role}@demo.local` for Westlands and `eleven-2-{role}@demo.local` for Kasarani. Role identifiers: `waiter`, `stockkeeper`, `controller` (Accountant), `kitchen` (Chef). New local-demo identities use password `LocalEleven2026!`. Their local PINs are in the untracked `.tmp/eleven-demo-staff.json`; no original account's password/PIN was reset.
- Eight new branch-linked demo staff identities were added; original sales, stock, expenses and orders were not reseeded. `execution/provision_eleven_demo_staff.py` defaults to dry-run, is restricted to this named local DB and never resets an existing identity.
- The system drive filled during validation. Large generated build caches and installed frontend dependencies were moved to `D:/codex-eleven-runtime/2026-10-25/` with junctions preserving the original ignored paths. Temporary validation files also use that dedicated D: folder. Application source and database remain in the original workspace.

## Product limits still requiring follow-through

1. Final primary-surface phone/desktop and retry/filter checks are completed in the 26 October follow-through above. Optional legacy administration screens retain older presentation and were not exhaustively reviewed.
2. Validate real client POS and statement samples. Generated records and deterministic reconciliation tests do not establish provider compatibility or statement coverage semantics.
3. Receipt batches store received quantity and optional expiry, not remaining-lot/FIFO stock. Historical dates remain unknown. Negative or unallocated zone balances identify recording work and are not theft findings.
4. New location evidence submits online; existing manual/offline queues are preserved. The current drawer model is restaurant-wide, with explicit non-overlapping assignments; separate physical drawers need an additional drawer identity contract.
5. Existing raw administration and optional legacy staff modules remain accessible and retain some older presentation. Optional external notification delivery and consent-reviewed campaigns remain unconfigured and unexecuted.
6. Per-item history has bounded recent previews (50 location events, 30 movements, 30 batches); dedicated searchable paging for older detail records remains to be built. Financial accounting/export paths remain available separately.

No universal zero-bugs or production-readiness claim is made. Graphify was unavailable on this host; the full repository sprint gate was not run or claimed.
