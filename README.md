# MASAR — Odoo 19

**شركة مسار العالمية للأنظمة والحلول المالية**  
Brand: **MASAR**

Independent Odoo 19 Community deployment prepared from the Rasd Odoo 19 source tree, without operational databases or filestore data.

## Stack

- Odoo 19.0 (Community)
- PostgreSQL (Railway plugin)
- Persistent volume at `/var/lib/odoo` (filestore + sessions)
- Custom addon: `custom_addons/masar_brand`

## Native apps prepared on first boot

- Contacts
- CRM
- Sales (`sale_management`)
- Accounting (`account`) + Analytics
- Project
- Employees (`hr`)
- Calendar
- Website + Website CRM
- Email Marketing (`mass_mailing`)
- Dashboards (`board`)
- Saudi localization (`l10n_sa`)
- MASAR brand (`masar_brand`)

Languages: Arabic (`ar_001`, RTL) + English (`en_US`).

## Railway

Build uses the root `Dockerfile`. Required service variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Provided by Railway PostgreSQL |
| `ODOO_DB_NAME` | Defaults to `masar` |
| `ODOO_ADMIN_PASSWD` | Master DB manager password |
| `PORT` | Provided by Railway (HTTP) |

Optional:

- `ODOO_FORCE_INIT=1` — force re-init (destructive)
- `ODOO_UPDATE_MODULES=1` — run `-u` on start
- `ODOO_WORKERS` — multi-worker mode (default `0` for Railway)

Volume mount (see `railway.toml`): `masar_odoo_data` → `/var/lib/odoo`.

## Local run (Docker)

```bash
docker build -t masar-odoo .
docker run --rm -p 8069:8069 \
  -e DATABASE_URL=postgres://odoo:odoo@host:5432/postgres \
  -e ODOO_DB_NAME=masar \
  -e ODOO_ADMIN_PASSWD=admin \
  -v masar_data:/var/lib/odoo \
  masar-odoo
```

Default login after first init: `admin` / `admin` (change immediately).

## Repository layout

```
addons/           # Odoo community apps
odoo/             # Odoo server core
custom_addons/    # MASAR-only custom modules
docker/           # entrypoint, conf template, bootstrap
Dockerfile
railway.toml
requirements.txt
odoo-bin
```

No production DB dumps, filestore, or runtime secrets are stored in this repository.
