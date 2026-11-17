#!/usr/bin/env bash
# Retire Odoo modules whose code was removed from the repository.
#
# Such modules stay "installed" in the database; clicking Upgrade leaves them
# stuck on "Upgrading" forever because Odoo cannot find their code. This script:
#   1. refuses to run if a module that still has code depends on them,
#   2. backs the database up (pg_dump -Fc) into the current folder,
#   3. marks the modules uninstalled and switches off their leftover views,
#      menus and scheduled jobs (nothing is deleted; their data stays),
#   4. restarts Odoo.
#
# Usage (on the server, with sudo):
#   sudo bash remove-missing-modules.sh DBNAME
#   sudo bash remove-missing-modules.sh DBNAME inventory sale_approval_workflow ...
# Environment overrides: DB_CONTAINER (odoo-db-1), ODOO_CONTAINER (odoo-odoo-1), PGUSER (odoo).
#
# Undo: restore the backup printed at step 2:
#   docker exec -i odoo-db-1 pg_restore -U odoo -c -d DBNAME < BACKUP_FILE
set -euo pipefail

DB="${1:?Give the database name, e.g.: sudo bash remove-missing-modules.sh ddfsc}"
shift
MODULES=("$@")
if [ ${#MODULES[@]} -eq 0 ]; then
    MODULES=(inventory sale_approval_workflow sales_customer_credit_limit sales_discount_rule)
fi
DB_CONTAINER="${DB_CONTAINER:-odoo-db-1}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo-odoo-1}"
PGUSER="${PGUSER:-odoo}"

LIST=$(printf "'%s'," "${MODULES[@]}"); LIST="(${LIST%,})"
psql_run() { docker exec -i "$DB_CONTAINER" psql -U "$PGUSER" -d "$DB" -v ON_ERROR_STOP=1 "$@"; }

echo "== Modules to retire in database '$DB': ${MODULES[*]}"
psql_run -c "SELECT name, state FROM ir_module_module WHERE name IN $LIST ORDER BY name;"

echo "== Checking that no module with code still depends on them..."
BLOCKERS=$(psql_run -At -c "
    SELECT DISTINCT m.name FROM ir_module_module_dependency d
      JOIN ir_module_module m ON m.id = d.module_id
     WHERE d.name IN $LIST AND m.name NOT IN $LIST
       AND m.state IN ('installed', 'to upgrade', 'to install');")
if [ -n "$BLOCKERS" ]; then
    echo "STOP: these installed modules depend on them: $BLOCKERS"
    echo "Add them to the list only if their code was removed too, otherwise ask the developer."
    exit 1
fi
echo "   none."

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
echo "Done. Reload Odoo in the browser: the modules no longer show as Upgrading."
echo "Backup kept at: $(pwd)/$BACKUP"
