#!/usr/bin/env sh
set -eu
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump --format=custom --no-owner --no-acl --file="$OUT_DIR/developer-os-$STAMP.dump" "$POSTGRES_DB"
unset PGPASSWORD
echo "Created $OUT_DIR/developer-os-$STAMP.dump"
