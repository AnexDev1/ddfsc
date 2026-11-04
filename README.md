# DDFSC Odoo 19 Deployment

This repository root is the **custom-addon source**. Docker mounts it at
`/mnt/extra-addons`; do not create another nested `custom_addons` directory.
The deployable set includes DDFSC Manufacturing, Quality Control, HR &
Attendance, Ethiopian Payroll, and their required OCA dependency modules.
They are listed in `custom-modules.txt` and are versioned together in Git.

## Fresh computer setup

1. Clone this repository.
2. Copy `.env.example` to `.env` and choose a strong PostgreSQL password.
3. Copy `config/odoo.conf.example` to `config/odoo.conf` and choose a strong Odoo master password.
4. Start the stack: `docker compose up -d --build`.
5. Create the target database in Odoo, then install the complete approved module set:

   ```sh
   docker compose exec -T odoo sh /mnt/extra-addons/scripts/install-custom-modules.sh ddfsc install
   ```

Replace `ddfsc` with the actual database name if it differs.

## Updating an existing installation

```sh
git pull --ff-only
docker compose up -d --build
docker compose exec -T odoo sh /mnt/extra-addons/scripts/install-custom-modules.sh ddfsc upgrade
docker compose restart odoo
```

Open `http://localhost:8069` after starting the services. PostgreSQL and Odoo
data persist in Docker volumes, so `docker compose stop` does not delete them.
