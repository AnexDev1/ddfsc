#!/usr/bin/env bash
# Daily backup of every Odoo database on this server: the database itself and its
# filestore (attachments, images, PDFs). Old backups are deleted after KEEP_DAYS.
#
# Set up once (on the server, with sudo, from the repository folder):
#   sudo bash scripts/backup-odoo.sh --install-cron   # back up every night at 02:00
#   sudo bash scripts/backup-odoo.sh                  # take a backup now (also a good test)
#   sudo bash scripts/backup-odoo.sh --list           # show the backups kept
#
# Each run creates BACKUP_DIR/<date>_<time>/ with, for every database:
#   <db>.dump               the database (pg_dump custom format)
#   <db>-filestore.tar.gz   its attachments
# Restore one with scripts/restore-odoo-backup.sh.
#
# Settings (environment variables, or edit the defaults below):
#   BACKUP_DIR      where backups go                       (/opt/odoo-backups)
#   KEEP_DAYS       days of backups to keep                (14)
#   COPY_TO         optional second folder, e.g. a USB disk or network share mounted
#                   on the server; each backup is copied there too (kept KEEP_DAYS as well)
#   DB_CONTAINER    database container                     (odoo-db-1)
#   ODOO_CONTAINER  Odoo container                         (odoo-odoo-1)
#   PGUSER          database user                          (odoo)
#   BACKUP_TIME     cron time used by --install-cron        ("0 2 * * *" = 02:00 every day)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/odoo-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
COPY_TO="${COPY_TO:-}"
DB_CONTAINER="${DB_CONTAINER:-odoo-db-1}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo-odoo-1}"
PGUSER="${PGUSER:-odoo}"
BACKUP_TIME="${BACKUP_TIME:-0 2 * * *}"
FILESTORE="/var/lib/odoo/filestore"
SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

case "${1:-}" in
    --install-cron)
        cat > /etc/cron.d/odoo-backup <<CRON
# Daily Odoo backup (installed by $SCRIPT)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
BACKUP_DIR=$BACKUP_DIR
KEEP_DAYS=$KEEP_DAYS
COPY_TO=$COPY_TO
DB_CONTAINER=$DB_CONTAINER
ODOO_CONTAINER=$ODOO_CONTAINER
PGUSER=$PGUSER
$BACKUP_TIME root bash $SCRIPT >> /var/log/odoo-backup.log 2>&1
CRON
        chmod 644 /etc/cron.d/odoo-backup
        echo "Installed: /etc/cron.d/odoo-backup runs '$BACKUP_TIME' (minute hour ...)."
        echo "Backups go to $BACKUP_DIR, kept $KEEP_DAYS days. Log: /var/log/odoo-backup.log"
        echo "Run 'sudo bash $SCRIPT' once now to check that a backup works."
        exit 0 ;;
    --list)
        ls -1 "$BACKUP_DIR" 2>/dev/null | sed 's/^/   /' || true
        du -sh "$BACKUP_DIR" 2>/dev/null || echo "No backups yet in $BACKUP_DIR."
        exit 0 ;;
    "") ;;
    *) echo "Unknown option: $1 (use --install-cron, --list, or nothing)"; exit 1 ;;
esac

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

STAMP="$(date +%Y-%m-%d_%H%M)"
TARGET="$BACKUP_DIR/$STAMP"
mkdir -p "$TARGET"
chmod 700 "$BACKUP_DIR"
log "Backup started -> $TARGET"

DATABASES=$(docker exec "$DB_CONTAINER" psql -U "$PGUSER" -d postgres -Atc \
    "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY datname")
[ -n "$DATABASES" ] || { log "FAILED: no database found in $DB_CONTAINER"; exit 1; }

FAILED=0
for db in $DATABASES; do
    # 1. Database
    if docker exec "$DB_CONTAINER" pg_dump -U "$PGUSER" -Fc "$db" > "$TARGET/$db.dump" \
            && [ -s "$TARGET/$db.dump" ] \
            && docker exec -i "$DB_CONTAINER" pg_restore -l < "$TARGET/$db.dump" > /dev/null; then
        log "  $db: database ok ($(du -h "$TARGET/$db.dump" | cut -f1))"
    else
        log "  $db: DATABASE BACKUP FAILED"; FAILED=1
    fi
    # 2. Filestore (attachments)
    if docker exec "$ODOO_CONTAINER" test -d "$FILESTORE/$db"; then
        if docker exec "$ODOO_CONTAINER" tar -C "$FILESTORE" -czf - "$db" > "$TARGET/$db-filestore.tar.gz" \
                && gzip -t "$TARGET/$db-filestore.tar.gz"; then
            log "  $db: filestore ok ($(du -h "$TARGET/$db-filestore.tar.gz" | cut -f1))"
        else
            log "  $db: FILESTORE BACKUP FAILED"; FAILED=1
        fi
    else
        log "  $db: no filestore folder (nothing attached yet)"
    fi
done
chmod -R go-rwx "$TARGET"

if [ -n "$COPY_TO" ]; then
    if mkdir -p "$COPY_TO" && cp -r "$TARGET" "$COPY_TO/"; then
        log "Copied to $COPY_TO/$STAMP"
        find "$COPY_TO" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +"$KEEP_DAYS" -exec rm -rf {} +
    else
        log "COPY TO $COPY_TO FAILED (is the disk mounted?)"; FAILED=1
    fi
fi

# Delete backups older than KEEP_DAYS (only folders this script made: 20YY-MM-DD_HHMM).
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +"$KEEP_DAYS" -exec rm -rf {} +

if [ "$FAILED" -ne 0 ]; then
    log "Backup finished WITH ERRORS (see above)"; exit 1
fi
log "Backup finished: $(du -sh "$TARGET" | cut -f1) in $TARGET"
