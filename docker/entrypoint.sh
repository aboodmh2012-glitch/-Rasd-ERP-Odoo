#!/usr/bin/env bash
set -euo pipefail

# MASAR entrypoint for official odoo:19 image on Railway.
ODOO_BIN_PATH="${ODOO_BIN_PATH:-/usr/bin/odoo}"
ODOO_DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo}"
ODOO_RC="${ODOO_RC:-/etc/odoo/odoo.conf}"
TEMPLATE="${ODOO_CONF_TEMPLATE:-/etc/odoo/odoo.conf.template}"
LOGFILE="${ODOO_LOG_FILE:-/var/log/odoo/odoo.log}"
INIT_SCRIPT="${MASAR_INIT_SCRIPT:-/opt/masar/init_masar.py}"

mkdir -p "${ODOO_DATA_DIR}/filestore" "${ODOO_DATA_DIR}/sessions" "$(dirname "${LOGFILE}")"

eval "$(
python3 - <<'PY'
import os, urllib.parse, shlex
url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_PRIVATE_URL") or ""
if url:
    u = urllib.parse.urlparse(url)
    vals = {
        "DB_HOST": u.hostname or "",
        "DB_PORT": str(u.port or 5432),
        "DB_USER": urllib.parse.unquote(u.username or ""),
        "DB_PASSWORD": urllib.parse.unquote(u.password or ""),
        "DB_NAME_FROM_URL": (u.path or "").lstrip("/"),
    }
else:
    vals = {
        "DB_HOST": os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST") or "",
        "DB_PORT": os.environ.get("PGPORT") or os.environ.get("POSTGRES_PORT") or "5432",
        "DB_USER": os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER") or "odoo",
        "DB_PASSWORD": os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD") or "",
        "DB_NAME_FROM_URL": os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB") or "",
    }
for k, v in vals.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

DB_NAME="${ODOO_DB_NAME:-masar}"
if [[ -z "${ODOO_DB_NAME:-}" && "${DB_NAME_FROM_URL}" != "" && "${DB_NAME_FROM_URL}" != "railway" && "${DB_NAME_FROM_URL}" != "postgres" ]]; then
  DB_NAME="${DB_NAME_FROM_URL}"
fi

ADMIN_PASSWD="${ODOO_ADMIN_PASSWD:-${ODOO_ADMIN_PASSWORD:-admin}}"
HTTP_PORT="${PORT:-8069}"
WORKERS="${ODOO_WORKERS:-0}"
PROXY_MODE="${ODOO_PROXY_MODE:-True}"
LIST_DB="${ODOO_LIST_DB:-False}"
DB_FILTER="${ODOO_DB_FILTER:-^${DB_NAME}$}"
WITHOUT_DEMO="${ODOO_WITHOUT_DEMO:-all}"
INIT_MODULES="${ODOO_INIT_MODULES:-base,web,contacts,crm,sale_management,account,analytic,project,hr,calendar,website,website_crm,mass_mailing,board,l10n_sa,masar_brand}"
LOAD_LANG="${ODOO_LOAD_LANG:-ar_001,en_US}"

if [[ -z "${DB_HOST}" || -z "${DB_USER}" ]]; then
  echo "[masar] ERROR: Database host/user missing. Set DATABASE_URL (Railway Postgres)." >&2
  exit 1
fi

export PGPASSWORD="${DB_PASSWORD}"

echo "[masar] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 90); do
  if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" >/dev/null 2>&1; then
    echo "[masar] PostgreSQL is ready."
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    echo "[masar] ERROR: PostgreSQL not reachable after 90 attempts." >&2
    exit 1
  fi
  sleep 2
done

DB_EXISTS="$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" || true)"
if [[ "${DB_EXISTS}" != "1" ]]; then
  echo "[masar] Creating PostgreSQL database '${DB_NAME}'..."
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\" ENCODING 'UTF8' TEMPLATE template0;"
fi

export DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME ADMIN_PASSWD HTTP_PORT WORKERS PROXY_MODE LIST_DB DB_FILTER ODOO_DATA_DIR LOGFILE
python3 - <<'PY'
import os
from pathlib import Path
template = Path(os.environ.get("ODOO_CONF_TEMPLATE", "/etc/odoo/odoo.conf.template")).read_text()
mapping = {k: os.environ[k] for k in [
    "DB_HOST","DB_PORT","DB_USER","DB_PASSWORD","DB_NAME","ADMIN_PASSWD",
    "HTTP_PORT","WORKERS","PROXY_MODE","LIST_DB","DB_FILTER","ODOO_DATA_DIR","LOGFILE",
]}
out = Path(os.environ.get("ODOO_CONF_TEMPLATE", "/etc/odoo/odoo.conf.template")).read_text()
for key, value in mapping.items():
    out = out.replace("${" + key + "}", str(value))
Path(os.environ.get("ODOO_RC", "/etc/odoo/odoo.conf")).write_text(out)
print("[masar] Wrote", os.environ.get("ODOO_RC", "/etc/odoo/odoo.conf"))
PY

ODOO_BIN=("${ODOO_BIN_PATH}" -c "${ODOO_RC}")

BASE_READY="$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc \
  "SELECT 1 FROM information_schema.tables WHERE table_name='ir_module_module' LIMIT 1" 2>/dev/null || true)"

if [[ "${BASE_READY}" != "1" || "${ODOO_FORCE_INIT:-0}" == "1" ]]; then
  echo "[masar] Initializing clean Odoo database '${DB_NAME}' with modules: ${INIT_MODULES}"
  "${ODOO_BIN[@]}" -d "${DB_NAME}" -i "${INIT_MODULES}" --without-demo="${WITHOUT_DEMO}" --load-language="${LOAD_LANG}" --stop-after-init
  echo "[masar] Applying MASAR company / language / website bootstrap..."
  "${ODOO_BIN[@]}" shell -d "${DB_NAME}" --stop-after-init < "${INIT_SCRIPT}"
else
  echo "[masar] Existing Odoo database detected — skipping -i init (persistence preserved)."
  if [[ "${ODOO_UPDATE_MODULES:-0}" == "1" ]]; then
    echo "[masar] Updating modules: ${ODOO_UPDATE_MODULE_LIST:-masar_brand}"
    "${ODOO_BIN[@]}" -d "${DB_NAME}" -u "${ODOO_UPDATE_MODULE_LIST:-masar_brand}" --stop-after-init
  fi
fi

if [[ "${1:-odoo}" == "odoo" ]]; then
  echo "[masar] Starting Odoo 19 (MASAR) on port ${HTTP_PORT}..."
  exec "${ODOO_BIN[@]}" -d "${DB_NAME}"
fi

exec "$@"
