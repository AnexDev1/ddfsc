#!/usr/bin/env bash
# Find and retire Odoo modules whose code was removed from the server.
#
# Such modules stay "installed" in the database; clicking Upgrade leaves them
# stuck on "Upgrading" forever because Odoo cannot find their code. This script:
#   1. asks the running Odoo container which modules it has code for (using the
#      same addons path the server runs with) and lists every installed module
#      that has none,
#   2. refuses to run if a module that still has code depends on them,
#   3. asks you to confirm, then backs the database up (pg_dump -Fc) into the
#      current folder,
#   4. marks the modules uninstalled and switches off their leftover views,
#      menus and scheduled jobs (nothing is deleted; their data stays),
#   5. restarts Odoo.
#
# Usage (on the server, with sudo):
#   sudo bash remove-missing-modules.sh DBNAME --list    # only show what would be retired
#   sudo bash remove-missing-modules.sh DBNAME           # find them all, confirm, retire
#   sudo bash remove-missing-modules.sh DBNAME -y        # same, without the question
#   sudo bash remove-missing-modules.sh DBNAME mod1 mod2 # retire exactly these modules
# Environment overrides: DB_CONTAINER (odoo-db-1), ODOO_CONTAINER (odoo-odoo-1), PGUSER (odoo).
#
# To also remove their groups, menus, fields and their line in Apps, use
# purge-missing-modules.sh instead.
#
# Undo: restore the backup printed at step 3:
#   docker exec -i odoo-db-1 pg_restore -U odoo -c -d DBNAME < BACKUP_FILE
set -euo pipefail

DB="${1:?Give the database name, e.g.: sudo bash remove-missing-modules.sh ddfsc --list}"
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

psql_run() { docker exec -i "$DB_CONTAINER" psql -U "$PGUSER" -d "$DB" -v ON_ERROR_STOP=1 "$@"; }

# Prints the name of every module Odoo has code for, using the addons path and
# config file of the Odoo process running in the container.
modules_with_code() {
    docker exec -i "$ODOO_CONTAINER" python3 - <<'PY'
import os, sys
args, conf = [], None
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        cmd = open('/proc/%s/cmdline' % pid, 'rb').read().decode(errors='ignore').split('\0')
    except OSError:
        continue
    if not any('odoo' in part for part in cmd[:3]):
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
conf = conf or os.environ.get('ODOO_RC') or '/etc/odoo/odoo.conf'
if os.path.exists(conf):
    args = ['-c', conf] + args
from odoo.tools import config
config.parse_config(args)
import odoo.addons
import odoo.modules.module as module
module.initialize_sys_path()
paths = list(odoo.addons.__path__)
print('addons path: ' + ', '.join(paths), file=sys.stderr)
names = set()
for path in paths:
    if os.path.isdir(path):
        for name in os.listdir(path):
            if os.path.isfile(os.path.join(path, name, '__manifest__.py')):
                names.add(name)
print('\n'.join(sorted(names)))
PY
}

if [ ${#MODULES[@]} -eq 0 ]; then
    echo "== Asking Odoo ($ODOO_CONTAINER) which modules have code..."
    ON_DISK=$(modules_with_code)
    COUNT=$(printf '%s\n' "$ON_DISK" | grep -c . || true)
    echo "   $COUNT modules found on disk."
    # Safety net: if the addons path could not be read, almost everything would look missing.
    for core in base web mail stock; do
        printf '%s\n' "$ON_DISK" | grep -qx "$core" || {
            echo "STOP: core module '$core' was not found on disk, so the addons path was not read correctly."
            echo "Nothing was changed. Pass the module names yourself instead."
            exit 1
        }
    done
    INSTALLED=$(psql_run -At -c "SELECT name FROM ir_module_module
        WHERE state IN ('installed', 'to upgrade', 'to remove', 'to install') ORDER BY name;")
    mapfile -t MODULES < <(comm -23 <(printf '%s\n' "$INSTALLED" | sort -u) \
                                    <(printf '%s\n' "$ON_DISK" | sort -u) | grep . || true)
    if [ ${#MODULES[@]} -eq 0 ]; then
        echo "Every installed module has code. Nothing to do."
        exit 0
    fi
fi

LIST=$(printf "'%s'," "${MODULES[@]}"); LIST="(${LIST%,})"
echo "== Modules without code in database '$DB' (${#MODULES[@]}):"
psql_run -c "SELECT name, state, shortdesc->>'en_US' AS title FROM ir_module_module
              WHERE name IN $LIST ORDER BY name;"

echo "== Checking that no module with code still depends on them..."
BLOCKERS=$(psql_run -At -c "
    SELECT DISTINCT m.name || ' (needs ' || d.name || ')' FROM ir_module_module_dependency d
      JOIN ir_module_module m ON m.id = d.module_id
     WHERE d.name IN $LIST AND m.name NOT IN $LIST
       AND m.state IN ('installed', 'to upgrade', 'to install');")
if [ -n "$BLOCKERS" ]; then
    echo "STOP: these installed modules depend on them:"
    echo "$BLOCKERS"
    echo "Ask the developer: either restore the missing code or retire these modules too."
    exit 1
fi
echo "   none."

if [ "$LIST_ONLY" -eq 1 ]; then
    echo "List only: nothing was changed. Run again without --list to retire them."
    exit 0
fi
if [ "$ASSUME_YES" -ne 1 ]; then
    read -r -p "Retire these ${#MODULES[@]} modules? Type yes to continue: " answer
    [ "$answer" = "yes" ] || { echo "Nothing was changed."; exit 1; }
fi

BACKUP="${DB}-before-module-removal-$(date +%Y%m%d-%H%M%S).dump"
echo "== Backing up '$DB' to $(pwd)/$BACKUP ..."
docker exec "$DB_CONTAINER" pg_dump -U "$PGUSER" -Fc "$DB" > "$BACKUP"
[ -s "$BACKUP" ] || { echo "STOP: the backup is empty, nothing was changed."; exit 1; }
echo "   done ($(du -h "$BACKUP" | cut -f1))."

echo "== Retiring the modules (one transaction)..."
psql_run <<SQL
BEGIN;
UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL WHERE name IN $LIST;
UPDATE ir_ui_view SET active = false
 WHERE active AND id IN (SELECT res_id FROM ir_model_data WHERE model = 'ir.ui.view' AND module IN $LIST);
UPDATE ir_ui_menu SET active = false
 WHERE active AND id IN (SELECT res_id FROM ir_model_data WHERE model = 'ir.ui.menu' AND module IN $LIST);
UPDATE ir_cron SET active = false
 WHERE active AND id IN (SELECT res_id FROM ir_model_data WHERE model = 'ir.cron' AND module IN $LIST);
SELECT name, state FROM ir_module_module WHERE name IN $LIST ORDER BY name;
COMMIT;
SQL

echo "== Restarting Odoo ($ODOO_CONTAINER)..."
docker restart "$ODOO_CONTAINER" >/dev/null
echo "Done. Reload Odoo in the browser: these modules no longer show as installed or Upgrading."
echo "Backup kept at: $(pwd)/$BACKUP"
