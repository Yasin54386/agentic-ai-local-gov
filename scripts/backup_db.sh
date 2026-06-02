#!/usr/bin/env bash
# Backup the Ask Territory SQLite database.
# Safe to run while the app is running (uses SQLite's .dump which is
# consistent even with concurrent writes in WAL mode).
#
# Usage:
#   bash scripts/backup_db.sh                   # backup to ./backups/
#   BACKUP_DIR=/var/backups/ask-territory bash scripts/backup_db.sh
#
# Add to crontab for weekly backups:
#   0 3 * * 0 cd /opt/ask-territory && bash scripts/backup_db.sh >> /var/log/backup.log 2>&1

set -euo pipefail

DB_PATH="${DB_PATH:-data/askterritory.db}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"   # delete backups older than this

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/askterritory_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: database not found at $DB_PATH"
    exit 1
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backing up $DB_PATH → $BACKUP_FILE"
sqlite3 "$DB_PATH" .dump | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "  Done. Size: $SIZE"

# Remove backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "askterritory_*.sql.gz" -mtime "+${KEEP_DAYS}" -delete
REMAINING=$(find "$BACKUP_DIR" -name "askterritory_*.sql.gz" | wc -l)
echo "  Backups retained: $REMAINING"

echo "  Restore with: gunzip -c $BACKUP_FILE | sqlite3 data/askterritory.db"
