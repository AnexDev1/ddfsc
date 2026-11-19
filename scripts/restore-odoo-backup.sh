#!/usr/bin/env bash
# Restore an Odoo database (and its attachments) from a backup made by backup-odoo.sh.
#
# Usage (on the server, with sudo, from the repository folder):
#   sudo bash scripts/backup-odoo.sh --list                                   # pick a backup
#   sudo bash scripts/restore-odoo-backup.sh /opt/odoo-backups/2026-11-19_0200 DBNAME
#   sudo bash scripts/restore-odoo-backup.sh /opt/odoo-backups/2026-11-19_0200 DBNAME NEWNAME
#
# With NEWNAME the backup is restored next to the live database under that name (safe:
# nothing existing is touched; open it from the Odoo database selector to look at it).
# Without NEWNAME it REPLACES the live database. The current database and attachments are
# not deleted: they are renamed to DBNAME_before_restore_<time>, so you can go back.
#
# Environment overrides: DB_CONTAINER (odoo-db-1), ODOO_CONTAINER (odoo-odoo-1), PGUSER (odoo).
set -euo pipefail

FOLDER="${1:?Give the backup folder, e.g. /opt/odoo-backups/2026-11-19_0200}"
DB="${2:?Give the database name that was backed up, e.g. ddfsc}"
TARGET="${3:-$DB}"
DB_CONTAINER="${DB_CONTAINER:-odoo-db-1}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo-odoo-1}"
PGUSER="${PGUSER:-odoo}"
FILESTORE="/var/lib/odoo/filestore"
DUMP="$FOLDER/$DB.dump"
FILES="$FOLDER/$DB-filestore.tar.gz"
STAMP="$(date +%Y%m%d_%H%M%S)"
TEMP_DB="${TARGET}_restoring_$STAMP"
OLD_DB="${TARGET}_before_restore_$STAMP"

[ -s "$DUMP" ] || { echo "STOP: $DUMP not found or empty."; exit 1; }
psql_q() { docker exec "$DB_CONTAINER" psql -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -Atc "$1"; }
exists() { [ "$(psql_q "SELECT count(*) FROM pg_database WHERE datname = '$1'")" = "1" ]; }

if [ "$TARGET" = "$DB" ] && exists "$TARGET"; then
    echo "This REPLACES the live database '$TARGET' with the backup from $FOLDER."
    echo "The current one is kept as '$OLD_DB'. Everyone using Odoo is disconnected."
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing was changed."; exit 1; }
elif exists "$TARGET"; then
    echo "STOP: a database named '$TARGET' already exists. Choose another name."; exit 1
fi

echo "== Restoring the database into '$TEMP_DB' (Odoo keeps running meanwhile)..."
psql_q "CREATE DATABASE \"$TEMP_DB\" OWNER \"$PGUSER\"" > /dev/null
if ! docker exec -i "$DB_CONTAINER" pg_restore -U "$PGUSER" -d "$TEMP_DB" --no-owner --role="$PGUSER" < "$DUMP"; then
    psql_q "DROP DATABASE IF EXISTS \"$TEMP_DB\"" > /dev/null
    echo "STOP: the restore failed; nothing was changed."; exit 1
fi
echo "   done."

echo "== Switching databases..."
if exists "$TARGET"; then
    docker stop "$ODOO_CONTAINER" > /dev/null
    psql_q "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TARGET' AND pid <> pg_backend_pid()" > /dev/null
    psql_q "ALTER DATABASE \"$TARGET\" RENAME TO \"$OLD_DB\"" > /dev/null
    echo "   current database kept as '$OLD_DB'."
fi
psql_q "ALTER DATABASE \"$TEMP_DB\" RENAME TO \"$TARGET\"" > /dev/null
docker start "$ODOO_CONTAINER" > /dev/null 2>&1 || true

echo "== Restoring attachments..."
if [ -s "$FILES" ]; then
    docker exec -i "$ODOO_CONTAINER" sh -c '
        set -e
        store="$1"; db="$2"; target="$3"; old="$4"
        mkdir -p "$store/.restore_tmp"
        rm -rf "$store/.restore_tmp/$db"
        tar -C "$store/.restore_tmp" -xzf -
        if [ -d "$store/$target" ]; then mv "$store/$target" "$store/$old"; fi
        mv "$store/.restore_tmp/$db" "$store/$target"
        rmdir "$store/.restore_tmp" 2>/dev/null || true
    ' sh "$FILESTORE" "$DB" "$TARGET" "$OLD_DB" < "$FILES"
    echo "   done."
else
    echo "   no attachment archive in the backup; skipped."
fi

docker restart "$ODOO_CONTAINER" > /dev/null
echo "Done. '$TARGET' now holds the backup from $FOLDER."
if exists "$OLD_DB"; then
    echo "The previous database is kept as '$OLD_DB'. When you are sure, delete it from the"
    echo "Odoo database manager (/web/database/manager)."
fi
