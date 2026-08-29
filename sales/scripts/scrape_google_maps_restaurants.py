"""
Scrape restaurant listings from Google Maps search results for lead generation.

Usage:
    python sales/scripts/scrape_google_maps_restaurants.py --areas "Karen" "Lavington" --per-area 40
    python sales/scripts/scrape_google_maps_restaurants.py --areas-file areas.txt --per-area 60 --out .tmp/restaurants.csv

Notes:
- Uses Scrapling's DynamicFetcher (Chromium via patchright) to render Google Maps'
  JS-heavy results feed, scrolls the results panel to lazy-load more cards, then
  parses each card's DOM for name / rating / reviews / category / address / coords.
- Google Maps' internal class names (e.g. Nv2PK, hfpxzc) rotate periodically, so
  extraction leans on stable signals instead: role="feed"/role="article" landmarks,
  aria-label (holds the business name), and regex over the card's visible text runs.
- This only reads Maps' public search results page like a browser would; it does not
  authenticate, bypass paywalls, or defeat any bot-challenge. If Google serves a
  CAPTCHA/consent wall this script can't clear, it stops and reports rather than
  working around it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scrapling.fetchers import DynamicFetcher

RATING_RE = re.compile(r"^\d(?:[.,]\d)?$")
REVIEWS_RE = re.compile(r"^\(([\d,.\s]+)\)$")
COORD_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
# Bullet-only separators ("·"/"⋅"/"•") and icon-font ligature glyphs (Private Use
# Area codepoints, e.g. a clock/wheelchair icon rendered as "text") are noise —
# real DOM text nodes, but not content — so they're dropped before field parsing.
NOISE_RE = re.compile(r"^[\s·⋅•-]+$")


@dataclass
class Restaurant:
    query_area: str
    name: str
    rating: Optional[str]
    review_count: Optional[str]
    category: Optional[str]
    address_snippet: Optional[str]
    status_hours: Optional[str]
    maps_url: Optional[str]
    latitude: Optional[str]
    longitude: Optional[str]
    scraped_at: str


def build_search_url(query: str) -> str:
    # `hl=en` forces English UI strings (categories, hours text); Maps reads this
    # query param directly and otherwise defaults to the visitor's geo-inferred
    # locale (Swahili for a Kenyan IP), ignoring the browser's Accept-Language.
    return "https://www.google.com/maps/search/" + urllib.parse.quote(query) + "?hl=en"


def make_page_action(target_count: int, max_idle_rounds: int = 5, scroll_pause_ms: int = 1400):
    def action(page):
        # Dismiss EU/consent interstitial if it shows up.
        try:
            page.wait_for_timeout(1200)
            for label in ("Accept all", "I agree", "Reject all"):
                btn = page.locator(f'button:has-text("{label}")')
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(1000)
                    break
        except Exception:
            pass

        try:
            page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            return  # No results feed found (blocked page / zero results) — let caller see raw HTML.

        prev_count = 0
        idle_rounds = 0
        while idle_rounds < max_idle_rounds:
            page.evaluate(
                """() => {
                    const feed = document.querySelector('div[role="feed"]');
                    if (feed) feed.scrollTop = feed.scrollHeight;
                }"""
            )
            page.wait_for_timeout(scroll_pause_ms)

            count = page.evaluate(
                """() => document.querySelectorAll('div[role="feed"] > div a[aria-label]').length"""
            )
            if count >= target_count:
                break
            if count <= prev_count:
                idle_rounds += 1
            else:
                idle_rounds = 0
            prev_count = count

    return action


def parse_results(page, query_area: str) -> list[Restaurant]:
    scraped_at = datetime.now(timezone.utc).isoformat()
    rows = page.css('div[role="feed"] > div')
    out: list[Restaurant] = []
    seen_urls: set[str] = set()

    for row in rows:
        name = (row.css("a[aria-label]::attr(aria-label)").get() or "").strip()
        href = (row.css("a[aria-label]::attr(href)").get() or "").strip()
        if not name or not href or href in seen_urls:
            continue
        seen_urls.add(href)

        texts = [t.strip() for t in row.css("*::text").getall() if t and t.strip()]
        # Drop the name itself, bullet/icon-glyph noise, and de-dupe consecutive
        # identical runs (nested tags repeat text).
        cleaned: list[str] = []
        for t in texts:
            t = "".join(ch for ch in t if not (0xE000 <= ord(ch) <= 0xF8FF)).strip()
            if not t or t == name or NOISE_RE.match(t):
                continue
            if cleaned and cleaned[-1] == t:
                continue
            cleaned.append(t)

        rating = None
        review_count = None
        remainder: list[str] = []
        for t in cleaned:
            if rating is None and RATING_RE.match(t):
                rating = t.replace(",", ".")
                continue
            m = REVIEWS_RE.match(t)
            if review_count is None and m:
                review_count = m.group(1).replace(" ", "").replace(".", "").replace(",", "")
                continue
            remainder.append(t)

        category = remainder[0] if remainder else None
        address_snippet = remainder[1] if len(remainder) > 1 else None
        status_hours = " | ".join(remainder[2:]) if len(remainder) > 2 else None

        lat = lng = None
        coord_match = COORD_RE.search(href)
        if coord_match:
            lat, lng = coord_match.group(1), coord_match.group(2)

        out.append(
            Restaurant(
                query_area=query_area,
                name=name,
                rating=rating,
                review_count=review_count,
                category=category,
                address_snippet=address_snippet,
                status_hours=status_hours,
                maps_url=href,
                latitude=lat,
                longitude=lng,
                scraped_at=scraped_at,
            )
        )

    return out


def scrape_area(area: str, per_area: int, headless: bool, region_suffix: str) -> list[Restaurant]:
    query = f"restaurants in {area}" if region_suffix.lower() not in area.lower() else f"restaurants in {area}"
    if region_suffix and region_suffix.lower() not in query.lower():
        query = f"{query}, {region_suffix}"
    url = build_search_url(query)

    print(f"[scrape] {area!r} -> {url}", file=sys.stderr)
    page = DynamicFetcher.fetch(
        url,
        headless=headless,
        network_idle=True,
        wait_selector='div[role="feed"]',
        page_action=make_page_action(per_area),
        timeout=60000,
        disable_resources=True,
        google_search=False,
        locale="en-US",
        # A narrow viewport collapses Maps' result cards to a compact layout that
        # drops the review-count text entirely; force a wide one to keep it.
        additional_args={"viewport": {"width": 1440, "height": 1000}},
    )

    results = parse_results(page, area)
    if not results:
        debug_path = Path(".tmp") / f"debug_{re.sub(r'[^a-zA-Z0-9]+', '_', area)}.html"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(page.body if hasattr(page, "body") else str(page), encoding="utf-8")
        print(f"[scrape] 0 results for {area!r} — dumped page to {debug_path} for inspection", file=sys.stderr)

    print(f"[scrape] {area!r}: {len(results)} results", file=sys.stderr)
    return results[:per_area]


FIELDNAMES = [
    "query_area", "name", "rating", "review_count", "category",
    "address_snippet", "status_hours", "maps_url", "latitude", "longitude", "scraped_at",
]


def save_output(out_path: Path, rows: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    out_path.with_suffix(".json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Scrape restaurant leads from Google Maps by area.")
    parser.add_argument("--areas", nargs="+", help="Area/neighborhood names to search, e.g. Karen Lavington")
    parser.add_argument("--areas-file", type=Path, help="Text file with one area per line")
    parser.add_argument("--region-suffix", default="Nairobi, Kenya", help="Appended to each query for geo context")
    parser.add_argument("--per-area", type=int, default=40, help="Target max results to try to load per area")
    parser.add_argument("--out", type=Path, default=Path(".tmp/restaurants.csv"))
    parser.add_argument("--headful", action="store_true", help="Show the browser window (debugging)")
    parser.add_argument("--pause", type=float, default=3.0, help="Seconds to sleep between areas")
    parser.add_argument(
        "--resume", action="store_true",
        help="Load existing rows from --out first and append/dedupe new areas into the same file",
    )
    args = parser.parse_args()

    areas = list(args.areas or [])
    if args.areas_file:
        areas.extend(
            line.strip() for line in args.areas_file.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    if not areas:
        parser.error("Provide --areas and/or --areas-file")

    all_rows: list[dict] = []
    seen_keys: set[str] = set()

    if args.resume and args.out.exists():
        with args.out.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                all_rows.append(row)
                key = row.get("maps_url") or f"{row.get('name')}|{row.get('address_snippet')}"
                seen_keys.add(key)
        print(f"[scrape] resuming: loaded {len(all_rows)} existing rows from {args.out}", file=sys.stderr)

    for i, area in enumerate(areas):
        try:
            results = scrape_area(area, args.per_area, headless=not args.headful, region_suffix=args.region_suffix)
        except Exception as e:
            print(f"[scrape] FAILED for {area!r}: {e}", file=sys.stderr)
            continue

        new_count = 0
        for r in results:
            key = r.maps_url or f"{r.name}|{r.address_snippet}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_rows.append(asdict(r))
            new_count += 1
        print(f"[scrape] {area!r}: {new_count} new (of {len(results)}) — {len(all_rows)} total so far", file=sys.stderr)

        # Save after every area, not just at the end — a long multi-area run can be
        # interrupted (timeout, Ctrl-C, crash) and we don't want to lose progress.
        save_output(args.out, all_rows)

        if i < len(areas) - 1:
            time.sleep(args.pause)

    print(f"\nSaved {len(all_rows)} unique restaurants total -> {args.out} / {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
