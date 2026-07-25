"""
Enrich a restaurant leads CSV (produced by scrape_google_maps_restaurants.py) with
phone numbers and websites, by visiting each restaurant's individual Google Maps
place page (the list/search view never includes phone numbers).

Usage:
    python sales/scripts/enrich_phone_numbers.py --in leads/kenya_restaurants.csv --concurrency 8

Resumable: rows already carrying a phone value (including the "N/A" sentinel for
"we checked and this place has none listed") are skipped on rerun. Progress is
saved back to --in after every batch, so an interrupted run loses at most one
batch's worth of work.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
import sys
import time
from pathlib import Path

from scrapling.engines._browsers._controllers import AsyncDynamicSession

NO_PHONE_SENTINEL = "N/A"
EXTRA_FIELDS = ["phone", "website"]


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for field in EXTRA_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)
    for row in rows:
        for field in EXTRA_FIELDS:
            row.setdefault(field, "")
    return rows, fieldnames


def save_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    tmp_path = path.with_suffix(".csv.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    tmp_path.replace(path)


# Shared across all concurrent workers: once any worker sees a block, everyone
# pauses until this deadline instead of continuing to hammer a rate-limited IP,
# which otherwise just burns through the rest of the queue collecting nothing
# but 429s. Plain module-level state is fine here — single asyncio event loop.
_backoff_until = 0.0


async def fetch_one(session: AsyncDynamicSession, row: dict, timeout_ms: int) -> None:
    global _backoff_until
    url = row.get("maps_url")
    if not url:
        row["phone"] = NO_PHONE_SENTINEL
        return

    now = time.monotonic()
    if now < _backoff_until:
        await asyncio.sleep(_backoff_until - now)

    # Jitter to desynchronize the concurrent pool's requests a bit; a metronomic
    # burst of N requests/sec from one browser is more likely to trip Maps' rate
    # limiting than the same volume spread unevenly.
    await asyncio.sleep(random.uniform(0.2, 1.0))
    try:
        page = await session.fetch(
            url,
            network_idle=False,
            wait_selector="h1",
            wait_selector_state="attached",
            timeout=timeout_ms,
            disable_resources=True,
        )
    except Exception as e:
        print(f"[enrich] FAILED {row.get('name')!r}: {e}", file=sys.stderr)
        return  # leave phone blank so it's retried on the next --resume run

    # Google occasionally serves a CAPTCHA/rate-limit interstitial (HTTP 429, or a
    # redirect to google.com/sorry/...) instead of the place page. It has no h1 and
    # no tel: link, so without this check it looks identical to "no phone listed" -
    # that silently corrupted a lot of rows in an earlier run. Treat it as a failure
    # (leave blank, retry later) instead of recording it as a confirmed non-result,
    # and pause the whole pool for a cooldown so it stops digging the hole deeper.
    if getattr(page, "status", 200) == 429 or "/sorry/" in (getattr(page, "url", "") or ""):
        _backoff_until = max(_backoff_until, time.monotonic() + 120)
        print(f"[enrich] BLOCKED (rate-limited) {row.get('name')!r} — cooling down 120s", file=sys.stderr)
        return

    tel = page.css('a[href^="tel:"]::attr(href)').get()
    website = page.css('a[data-item-id="authority"]::attr(href)').get()
    row["phone"] = tel[4:] if tel else NO_PHONE_SENTINEL
    row["website"] = website or ""


async def run(path: Path, concurrency: int, timeout_ms: int, save_every: int, limit: int | None) -> None:
    rows, fieldnames = load_rows(path)
    pending = [r for r in rows if not r.get("phone")]
    if limit:
        pending = pending[:limit]
    total = len(pending)
    print(f"[enrich] {len(rows)} total rows, {total} need phone lookup", file=sys.stderr)
    if not total:
        return

    sem = asyncio.Semaphore(concurrency)
    done = 0
    start = time.monotonic()

    async def bounded(row: dict) -> None:
        nonlocal done
        async with sem:
            await fetch_one(session, row, timeout_ms)
        done += 1
        if done % save_every == 0:
            save_rows(path, rows, fieldnames)
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed else 0
            eta = (total - done) / rate if rate else 0
            print(
                f"[enrich] {done}/{total} done ({rate:.1f}/s, ETA {eta/60:.1f}m) — saved",
                file=sys.stderr,
            )

    async with AsyncDynamicSession(max_pages=concurrency, headless=True, disable_resources=True) as session:
        await asyncio.gather(*[bounded(r) for r in pending])

    save_rows(path, rows, fieldnames)
    have_phone = sum(1 for r in rows if r.get("phone") and r["phone"] != NO_PHONE_SENTINEL)
    print(f"[enrich] final save: {have_phone}/{len(rows)} rows have a real phone number", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Enrich restaurant CSV with phone numbers from Maps place pages.")
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=20000, help="Per-page timeout in ms")
    parser.add_argument("--save-every", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N pending rows (testing)")
    args = parser.parse_args()

    asyncio.run(run(args.in_path, args.concurrency, args.timeout, args.save_every, args.limit))


if __name__ == "__main__":
    main()
