#!/usr/bin/env bash
# Completely remove Odoo modules whose code is no longer on the server.
#
# remove-missing-modules.sh only marks such modules "not installed"; their
# line stays in Apps and their groups, menus and fields stay in the database.
# This script removes them for good, with Odoo's own uninstall:
#   groups and access rights, menus, views, actions, scheduled jobs, the
#   fields and tables they added (THEIR DATA IS DELETED), and finally their
#   line in the Apps list.
#
# Steps: list them -> stop if a module with code depends on them -> ask ->
# back the database up (pg_dump -Fc, current folder) -> remove -> restart Odoo.
#
# Usage (on the server, with sudo, from the repository folder):
#   sudo bash scripts/purge-missing-modules.sh DBNAME --list    # only show them
#   sudo bash scripts/purge-missing-modules.sh DBNAME           # confirm, then remove
#   sudo bash scripts/purge-missing-modules.sh DBNAME -y        # without the question
#   sudo bash scripts/purge-missing-modules.sh DBNAME mod1 mod2 # only these
# Environment overrides: DB_CONTAINER (odoo-db-1), ODOO_CONTAINER (odoo-odoo-1), PGUSER (odoo).
#
# Undo: restore the backup printed by the script:
#   docker exec -i odoo-db-1 pg_restore -U odoo -c -d DBNAME < BACKUP_FILE
set -euo pipefail

DB="${1:?Give the database name, e.g.: sudo bash scripts/purge-missing-modules.sh ddfsc --list}"
shift
LIST_ONLY=0; ASSUME_YES=0; MODULES=()
for arg in "$@"; do
    case "$arg" in
        --list) LIST_ONLY=1 ;;
        -y|--yes) ASSUME_YES=1 ;;
        *) MODULES+=("$arg") ;;
    esac
done
DB_CONTAINER="${DB_CONTAINER:-odoo-db-1}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo-odoo-1}"
PGUSER="${PGUSER:-odoo}"
PY="$(cd "$(dirname "$0")" && pwd)/purge_missing_modules.py"

# The addons path and config file of the Odoo process already running in the container.
mapfile -t ODOO_ARGS < <(docker exec -i "$ODOO_CONTAINER" python3 - <<'PY'
import os
args, conf = [], None
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        cmd = open('/proc/%s/cmdline' % pid, 'rb').read().decode(errors='ignore').split('\0')
    except OSError:
        continue
    if not any('odoo' in part for part in cmd[:3]) or 'shell' in cmd:
        continue
    for i, part in enumerate(cmd):
        nxt = cmd[i + 1] if i + 1 < len(cmd) else ''
        if part.startswith('--addons-path='):
            args.append(part)
        elif part == '--addons-path' and nxt:
            args.append('--addons-path=' + nxt)
        elif part.startswith('--config='):
            conf = part.split('=', 1)[1]
        elif part in ('-c', '--config') and nxt:
            conf = nxt
if conf:
    args.append('--config=' + conf)
if args:
    print('\n'.join(sorted(set(args))))
PY
)

run_odoo_shell() {   # $1 = 1 to apply, 0 to only list
    docker exec -i -e PURGE_APPLY="$1" -e PURGE_MODULES="${MODULES[*]:-}" "$ODOO_CONTAINER" \
        sh -c 'db="$1"; shift; exec odoo shell -d "$db" ${HOST:+--db_host="$HOST"} ${PORT:+--db_port="$PORT"} \
               ${USER:+--db_user="$USER"} ${PASSWORD:+--db_password="$PASSWORD"} --no-http "$@"' \
        sh "$DB" "${ODOO_ARGS[@]}" < "$PY" 2>/tmp/purge-missing-modules.log | grep '^PURGE' || true
}

echo "== Looking for modules without code in database '$DB'..."
RESULT=$(run_odoo_shell 0)
if [ -z "$RESULT" ]; then
    echo "STOP: Odoo shell gave no answer. Details: /tmp/purge-missing-modules.log"
    exit 1
fi
printf '%s\n' "$RESULT" | sed -n 's/^PURGE-MODULE /   /p'
if printf '%s\n' "$RESULT" | grep -q '^PURGE-STOP'; then
    printf '%s\n' "$RESULT" | sed -n 's/^PURGE-STOP /STOP: /p'
    echo "Nothing was changed."
    exit 1
fi
if printf '%s\n' "$RESULT" | grep -q '^PURGE-NOTHING'; then
    echo "Every module in the list has code. Nothing to do."
    exit 0
fi
COUNT=$(printf '%s\n' "$RESULT" | sed -n 's/^PURGE-FOUND //p')
if [ "$LIST_ONLY" -eq 1 ]; then
    echo "List only: nothing was changed. Run again without --list to remove these $COUNT modules."
    exit 0
fi
if [ "$ASSUME_YES" -ne 1 ]; then
    echo "These $COUNT modules, their groups, menus, fields, tables and DATA will be removed for good."
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing was changed."; exit 1; }
fi

BACKUP="${DB}-before-module-purge-$(date +%Y%m%d-%H%M%S).dump"
echo "== Backing up '$DB' to $(pwd)/$BACKUP ..."
docker exec "$DB_CONTAINER" pg_dump -U "$PGUSER" -Fc "$DB" > "$BACKUP"
[ -s "$BACKUP" ] || { echo "STOP: the backup is empty, nothing was changed."; exit 1; }
echo "   done ($(du -h "$BACKUP" | cut -f1))."

echo "== Removing them (Odoo uninstall, one transaction)..."
RESULT=$(run_odoo_shell 1)
if ! printf '%s\n' "$RESULT" | grep -q '^PURGE-DONE'; then
    echo "STOP: the removal did not finish; nothing was saved. Details: /tmp/purge-missing-modules.log"
    exit 1
fi
printf '%s\n' "$RESULT" | sed -n 's/^PURGE-DONE /   /p'

echo "== Restarting Odoo ($ODOO_CONTAINER)..."
docker restart "$ODOO_CONTAINER" >/dev/null
echo "Done. In Odoo: Apps > Update Apps List, then reload. The modules are gone from the list."
echo "Backup kept at: $(pwd)/$BACKUP"
