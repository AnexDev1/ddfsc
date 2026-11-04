#!/usr/bin/env sh
# Run inside the Odoo container through Docker Compose.
# Usage:
#   docker compose exec -T odoo sh /mnt/extra-addons/scripts/install-custom-modules.sh ddfsc install
#   docker compose exec -T odoo sh /mnt/extra-addons/scripts/install-custom-modules.sh ddfsc upgrade
set -eu

database="${1:?Provide the Odoo database name.}"
mode="${2:-install}"
modules="$(tr -d '\r\n' < /mnt/extra-addons/custom-modules.txt)"

case "$mode" in
    install) operation="-i" ;;
    upgrade) operation="-u" ;;
    *)
        echo "Mode must be 'install' or 'upgrade'." >&2
        exit 2
        ;;
esac

exec odoo -c /etc/odoo/odoo.conf -d "$database" "$operation" "$modules" --stop-after-init
