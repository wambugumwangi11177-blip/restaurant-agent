#!/usr/bin/env bash
# Restore a dump into a scratch database and prove it matches the source:
# per-table row counts must be identical. Drops the scratch database afterwards.
# Usage: DATABASE_URL=postgresql://... execution/restore_drill.sh <file.dump>
set -euo pipefail
DUMP="${1:?usage: restore_drill.sh <file.dump>}"
: "${DATABASE_URL:?DATABASE_URL must be set (the SOURCE database)}"
SRC="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"
SCRATCH_NAME="restore_drill_$(date -u +%s)"
BASE="${SRC%/*}"
SCRATCH="$BASE/$SCRATCH_NAME"

counts() {
  psql "$1" -At -c "SELECT string_agg(format('%s=%s', table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I', table_name), false, true, '')))[1]::text), ' ' ORDER BY table_name) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
}

psql "$BASE/postgres" -q -c "CREATE DATABASE \"$SCRATCH_NAME\""
trap 'psql "$BASE/postgres" -q -c "DROP DATABASE IF EXISTS \"$SCRATCH_NAME\" WITH (FORCE)"' EXIT
pg_restore --no-owner --no-privileges --dbname="$SCRATCH" "$DUMP"

A="$(counts "$SRC")"; B="$(counts "$SCRATCH")"
echo "source : $A"
echo "restore: $B"
if [[ "$A" == "$B" ]]; then echo "RESTORE DRILL PASSED"; else echo "RESTORE DRILL FAILED: row counts differ"; exit 1; fi
