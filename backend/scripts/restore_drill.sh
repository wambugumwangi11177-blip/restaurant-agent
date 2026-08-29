#!/usr/bin/env bash
# backend/scripts/restore_drill.sh
# ───────────────────────────────────
# Mechanizes DISASTER_RECOVERY.md §2 (steps 1-3): restore the latest backup
# into a THROWAWAY scratch database, run migrations against it, and confirm
# the app can boot against the restored data. Never touches production.
#
# Required env:
#   SCRATCH_DATABASE_URL — a scratch/throwaway Postgres instance. NEVER point
#                           this at production.
#   DUMP_FILE             — path to a .dump file produced by backup_db.sh
#                            (or downloaded from S3 first, e.g.
#                            `aws s3 cp s3://.../backup_XXXX.dump .`)
# Optional env:
#   HEALTH_URL            — base URL of an app instance pointed at
#                            SCRATCH_DATABASE_URL, for the /health/db check
#                            (default: http://localhost:8000)
#
# Usage:
#   DUMP_FILE=backup_20260716_120000.dump \
#   SCRATCH_DATABASE_URL=postgresql://user:pass@scratch-host:5432/scratch \
#     bash backend/scripts/restore_drill.sh
#
# Prints the wall-clock restore time (→ RTO) and the newest-row timestamps
# (→ RPO) so they can be recorded in DISASTER_RECOVERY.md §0.
set -euo pipefail

: "${SCRATCH_DATABASE_URL:?SCRATCH_DATABASE_URL must be set — a THROWAWAY database, never production}"
: "${DUMP_FILE:?DUMP_FILE must be set to a .dump file produced by backup_db.sh}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000}"

if [[ "$SCRATCH_DATABASE_URL" == *"prod"* ]]; then
  echo "[restore_drill] Refusing to run: SCRATCH_DATABASE_URL contains 'prod'. This script is for a throwaway DB only." >&2
  exit 1
fi

start_ts=$(date +%s)

echo "[restore_drill] Restoring ${DUMP_FILE} into scratch DB ..."
pg_restore --no-owner --clean --if-exists --dbname "$SCRATCH_DATABASE_URL" "$DUMP_FILE"

echo "[restore_drill] Running migrations against the restored DB ..."
DATABASE_URL="$SCRATCH_DATABASE_URL" alembic upgrade head

elapsed=$(( $(date +%s) - start_ts ))
echo "[restore_drill] Restore + migrate took ${elapsed}s — this is your RTO."

echo "[restore_drill] Checking ${HEALTH_URL}/health/db (point an app instance at SCRATCH_DATABASE_URL first) ..."
curl -sf "${HEALTH_URL}/health/db" && echo " -> OK" || echo " -> FAILED (is an app instance running against the scratch DB?)"

echo "[restore_drill] Newest-row timestamps (compare to when the backup was taken -> this is your RPO):"
psql "$SCRATCH_DATABASE_URL" -c "SELECT max(created_at) AS newest_order FROM orders;"
psql "$SCRATCH_DATABASE_URL" -c "SELECT max(created_at) AS newest_token_usage FROM token_usage;"
psql "$SCRATCH_DATABASE_URL" -c "SELECT max(consented_at) AS newest_consent FROM customer_consents;"

echo "[restore_drill] Done. Record the RTO/RPO above in DISASTER_RECOVERY.md §0, then tear down the scratch DB."
