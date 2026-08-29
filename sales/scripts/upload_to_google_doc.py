"""
Push the enriched restaurant leads CSV into a Google Doc.

Requires a Google Cloud OAuth client (see README note at bottom of this file for
how to obtain one) saved as credentials.json in the project root. On first run
this opens a browser for one-time consent and caches the result in token.json
(both are gitignored — see .gitignore) so later runs are non-interactive.

Usage:
    python sales/scripts/upload_to_google_doc.py --in leads/kenya_restaurants.csv --title "Kenya Restaurant Leads"
    python sales/scripts/upload_to_google_doc.py --in leads/kenya_restaurants.csv --doc-id <existing_doc_id>  # update in place
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/documents"]
CREDS_PATH = Path("credentials.json")
TOKEN_PATH = Path("token.json")


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                print(
                    f"[docs] Missing {CREDS_PATH}. Create an OAuth client (Desktop app type) in Google Cloud "
                    "Console for a project with the Google Docs API enabled, download it, and save it here "
                    "as credentials.json. See the note at the bottom of this script.",
                    file=sys.stderr,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_doc_text(rows: list[dict]) -> str:
    by_area: dict[str, list[dict]] = {}
    for row in rows:
        by_area.setdefault(row.get("query_area", "Other"), []).append(row)

    lines = [f"Kenya Restaurant Leads — {len(rows)} restaurants\n\n"]
    for area in sorted(by_area):
        lines.append(f"{area} ({len(by_area[area])})\n")
        for r in by_area[area]:
            phone = r.get("phone") or ""
            phone = "" if phone == "N/A" else phone
            bits = [r.get("name", "")]
            if r.get("rating"):
                bits.append(f"★{r['rating']}")
            if phone:
                bits.append(phone)
            if r.get("address_snippet"):
                bits.append(r["address_snippet"])
            lines.append("  • " + " — ".join(b for b in bits if b) + "\n")
        lines.append("\n")
    return "".join(lines)


def create_doc(service, title: str, text: str) -> str:
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
    ).execute()
    return doc_id


def update_doc(service, doc_id: str, text: str) -> None:
    doc = service.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"]
    requests = []
    if end_index > 2:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}})
    requests.append({"insertText": {"location": {"index": 1}, "text": text}})
    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def main():
    parser = argparse.ArgumentParser(description="Upload restaurant leads CSV to a Google Doc.")
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--title", default="Kenya Restaurant Leads")
    parser.add_argument("--doc-id", default=None, help="Update this existing doc instead of creating a new one")
    args = parser.parse_args()

    with args.in_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    text = build_doc_text(rows)
    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)

    if args.doc_id:
        update_doc(service, args.doc_id, text)
        doc_id = args.doc_id
    else:
        doc_id = create_doc(service, args.title, text)

    print(f"https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()

# --- How to get credentials.json (one-time, ~2 minutes, needs your Google account) ---
# 1. https://console.cloud.google.com/apis/library/docs.googleapis.com -> Enable, on any project
#    (create a new project first if you don't have one — it's free).
# 2. https://console.cloud.google.com/apis/credentials/consent -> configure the OAuth consent
#    screen as "External" + "Testing", add yourself as a test user.
# 3. https://console.cloud.google.com/apis/credentials -> Create Credentials -> OAuth client ID
#    -> Application type "Desktop app" -> Create -> Download JSON.
# 4. Save that file as credentials.json in this project's root directory.
# Running this script will then open your browser once for a one-click consent; after that
# it's cached in token.json and never asks again.
