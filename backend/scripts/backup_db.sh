#!/usr/bin/env bash
# backend/scripts/backup_db.sh
# ─────────────────────────────
# Logical (pg_dump) backup of the production Postgres DB, uploaded to S3/R2 —
# the "secondary — recommended" backup described in DISASTER_RECOVERY.md §1.
# Belt-and-suspenders against "provider account compromised / project
# deleted": the primary mechanism is still Railway/Neon's managed automatic
# backups, confirmed in their dashboard, not here.
#
# Required env:
#   DATABASE_URL      — Postgres connection string (a read-only role if possible)
#   BACKUP_S3_BUCKET   — target bucket (uploaded via `aws s3 cp`)
# Optional env:
#   BACKUP_S3_PREFIX   — key prefix within the bucket (default: db-backups)
#
# Usage: bash backend/scripts/backup_db.sh
# Invoked by .github/workflows/backup.yml on a daily schedule, or run by hand.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"
: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET must be set}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-db-backups}"

timestamp="$(date -u +%Y%m%d_%H%M%S)"
dump_file="backup_${timestamp}.dump"

echo "[backup_db] Dumping database to ${dump_file} ..."
pg_dump "$DATABASE_URL" --no-owner --format=custom --file "$dump_file"

echo "[backup_db] Uploading to s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}/${dump_file} ..."
aws s3 cp "$dump_file" "s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}/${dump_file}"

rm -f "$dump_file"
echo "[backup_db] Done. Set a lifecycle rule on the bucket/prefix to expire old backups (e.g. 30 days)."
