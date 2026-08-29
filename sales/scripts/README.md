# Sales / lead-generation scripts

Moved here 2026-07-25 from `execution/` (audit remediation, Module 6). All
five were added together in commit `4492c42` ("...and lead-gen scripts") —
they build and enrich a CSV of prospect restaurants (`leads/kenya_restaurants.csv`,
gitignored) for outbound sales, unrelated to the running product:

| script | what it does |
|---|---|
| `scrape_google_maps_restaurants.py` | scrapes candidate restaurant listings from Google Maps |
| `enrich_phone_numbers.py` | fills in phone/website per listing |
| `build_pdf.py` | renders the enriched CSV as a leads PDF |
| `build_local_docx.py` | same, as a `.docx` (stopgap while Google Docs upload is blocked on credentials) |
| `upload_to_google_doc.py` | pushes the CSV into a Google Doc (needs `credentials.json`, gitignored) |

They previously sat in `execution/` alongside the actual product's
deterministic tooling (`init_db.py`, `deploy_schema.py`, etc.), which read as
unfinished product scope on an audit — "document delivery" isn't a Chakula
feature; this is prospect outreach for the business itself. No code
elsewhere imports these (verified via grep before the move) — moving them
here is a pure relocation, not a behavior change.

Run from the repo root, e.g.:

```
python sales/scripts/build_pdf.py --in leads/kenya_restaurants.csv --out leads/kenya_restaurants.pdf
```
