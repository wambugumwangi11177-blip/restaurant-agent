# Figure 6.1 — Sixteen planted scenarios (transcribed from `LEVIII-v2-Build-Spec.pdf` p. 24)

The zip shipped with the spec has no `scenarios.png`; the picture exists only in the PDF. This is its text, so S2.2 and
E4 (`backend/tests/evals/test_e4_demo_scenarios.py`) have a source of truth in the repository.

| ID | Planted in the demo data | Engine must find | Shown on |
|---|---|---|---|
| P1 | Quarter chicken 400, cost 260 | profit leak · reprice to 435 | Zone 2 |
| P2 | Chips menu 300, avg charged 270 | sold below menu price | Zone 2 · Cash |
| P3 | Burger 600 on Glovo 25% | delivery keeps 170 vs 320 | Sales & Dishes |
| P4 | Afternoon 15–17h low margin | weakest hours | Sales & Dishes |
| P5 | Beef: kitchen uses 10 kg extra/week | missing stock in kitchen zone | Zone 2 · Store |
| P6 | Transfer: store 40 kg, kitchen 38 kg | handover doesn't match | Store |
| P7 | Tue night drawer short × 4 weeks | recurring pattern | Cash · Shift report |
| P8 | 3 'M-Pesa' sales, no statement line | M-Pesa gap (P6 phase) | Cash · Now alert |
| P9 | Gas +30% vs 3-month avg | costs going up | My Money |
| P10 | Rent 70k due on the 4th | bill radar shortfall | Zone 4 · Money |
| P11 | Nyama choma / Fish / Chips / Spaghetti | Star · Puzzle · Plowhorse · Dog | Sales & Dishes |
| P12 | Holiday Tuesday + chips out at 19:00 | why was Tuesday bad | OS · Reports |
| P13 | Kenchic delivers 56 of 60 | short delivery | Store |
| P14 | Branch B food cost 37% vs A 29% | branch comparison | OS compare |
| P15 | Supplier with one delivery | must NOT show 100% reliable | regression |
| P16 | POS orders without M-Pesa receipt | must NOT flood Home | regression |

"The demo generator plants each of these on purpose, with the same example numbers used in the client guide and video.
Eval E4 then asserts each one is detected by the real engine and appears in the right place. The two red rows (P15, P16)
are guards against old defects coming back."

S2.2 plants P1–P7 and P11–P16. P8 waits for the M-Pesa statement parser (S6.x); P9, P10 wait for the money layer (S3.x).
