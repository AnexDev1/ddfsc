# Local Odoo 19

Open http://localhost:8069 after starting the services.

Start: `docker compose up -d --build`
Stop: `docker compose stop`
Logs: `docker compose logs -f odoo`

The database creation master password is in `.env` as ODOO_MASTER_PASSWORD, and in config/odoo.conf as admin_passwd. Choose your own email and login password when creating a database.

Custom modules are cloned from https://github.com/AnexDev1/ddfsc into custom_addons and mounted at /mnt/extra-addons. After creating a database, enable developer mode, go to Apps, and Update Apps List. Remove the Apps filter to see modules that are not standalone applications. Install the modules you need.

Update module source: `git -C custom_addons pull --ff-only`, then `docker compose restart odoo`. Upgrade installed modules in Odoo after changing their source.

PostgreSQL and Odoo files persist in Docker volumes. `docker compose stop` retains them.

The recovered archive configuration is adapted in config/odoo.conf. Original recovered files are saved in archive_reference. No database backup could be recovered from the damaged archive; ddfsc is a fresh database. All 34 custom modules are installed. Administrator login credentials are in .env as ODOO_ADMIN_LOGIN and ODOO_ADMIN_PASSWORD. Installation warnings are recorded in install-addons.log.
