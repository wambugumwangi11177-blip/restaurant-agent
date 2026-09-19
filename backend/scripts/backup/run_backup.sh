#!/bin/sh
# Dump production Postgres and upload it to the Railway bucket.
#
# Fails loudly and early. A backup job that exits 0 having uploaded nothing is
# worse than no backup job: it manufactures the belief that you are covered.
# Every step is checked, and the object is verified present in the bucket
# before this reports success.
set -eu

: "${DATABASE_URL:?DATABASE_URL is not set}"
: "${BUCKET:?BUCKET is not set (the Railway bucket's S3 name)}"
: "${ENDPOINT:?ENDPOINT is not set (the Railway bucket's S3 endpoint)}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is not set}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is not set}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"

# Retention by COUNT, not age. Age-based pruning has a failure mode that count
# based pruning does not: if the cron stops running for longer than the window,
# the next successful run deletes every backup it has, because they are all now
# "too old". Keeping the newest N means a gap in the schedule can never empty
# the bucket.
KEEP="${KEEP_BACKUPS:-30}"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
FILE="backup-${STAMP}.dump"
LOCAL="/tmp/${FILE}"

echo "[backup] dumping database at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
# --format=custom is compressed and allows selective pg_restore.
# --no-owner so the dump restores into a scratch database owned by anyone,
# which is what a restore drill needs.
pg_dump "$DATABASE_URL" --format=custom --no-owner --file="$LOCAL"

SIZE="$(wc -c < "$LOCAL" | tr -d ' ')"
echo "[backup] dump complete: ${SIZE} bytes"

# A custom-format dump of even an empty schema is several KB. Smaller than that
# means pg_dump produced a stub — refuse to ship it and never let it push a
# good backup out of the retention window.
if [ "$SIZE" -lt 1024 ]; then
    echo "[backup] FATAL: dump is only ${SIZE} bytes — refusing to upload" >&2
    exit 1
fi

echo "[backup] uploading ${FILE} to s3://${BUCKET}/"
aws s3 cp "$LOCAL" "s3://${BUCKET}/${FILE}" --endpoint-url "$ENDPOINT"

# Prove it landed and is the right size. An upload can report success against a
# misconfigured endpoint in ways that leave nothing readable back.
REMOTE_SIZE="$(aws s3api head-object --bucket "$BUCKET" --key "$FILE" \
    --endpoint-url "$ENDPOINT" --query 'ContentLength' --output text)"
if [ "$REMOTE_SIZE" != "$SIZE" ]; then
    echo "[backup] FATAL: bucket holds ${REMOTE_SIZE} bytes, dumped ${SIZE}" >&2
    exit 1
fi
echo "[backup] verified in bucket: ${REMOTE_SIZE} bytes"

# Railway buckets have no lifecycle rules, so retention is our job. Filenames
# embed YYYYMMDD-HHMMSS, so a plain lexicographic sort is chronological — no
# date arithmetic, which busybox's `date` cannot do anyway.
#
# Pruning runs only AFTER a verified upload, so a failed run never deletes the
# last good backup.
echo "[backup] keeping the newest ${KEEP} backups"
aws s3 ls "s3://${BUCKET}/" --endpoint-url "$ENDPOINT" \
  | awk '{print $4}' \
  | grep -E '^backup-[0-9]{8}-[0-9]{6}\.dump$' \
  | sort -r \
  | tail -n "+$((KEEP + 1))" \
  | while read -r key; do
        echo "[backup]   removing ${key}"
        aws s3 rm "s3://${BUCKET}/${key}" --endpoint-url "$ENDPOINT"
    done

rm -f "$LOCAL"
echo "[backup] done — ${FILE} (${SIZE} bytes), keeping newest ${KEEP}"
