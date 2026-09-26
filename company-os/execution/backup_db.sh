#!/usr/bin/env bash
# Dump the database in pg_dump custom format to .tmp/backups/ (or $BACKUP_DIR).
# Usage: DATABASE_URL=postgresql://... execution/backup_db.sh
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL must be set}"
URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/.tmp/backups}"
mkdir -p "$DIR"
OUT="$DIR/company-os-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-privileges --dbname="$URL" --file="$OUT"
echo "$OUT"
