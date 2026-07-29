#!/bin/sh
# Instrumentированная инициализация Superset (debug session 973e83).
# Печатает маркеры гипотез H1–H5 и exit-коды каждого шага.

set -u

DEBUG_LOG="/app/superset_home/init-debug.ndjson"
mkdir -p /app/superset_home 2>/dev/null || true

log_ndjson() {
  # hypothesisId, message, data_json
  _ts=$(date +%s)000
  printf '{"sessionId":"973e83","hypothesisId":"%s","location":"superset/init.sh","message":"%s","data":%s,"timestamp":%s}\n' \
    "$1" "$2" "$3" "$_ts" | tee -a "$DEBUG_LOG"
}

echo "===== KDBL SUPERSET INIT START ====="
log_ndjson "META" "init_start" "{\"pwd\":\"$(pwd)\"}"

# H2: SECRET_KEY / config loading
echo "----- H2: SECRET_KEY / SUPERSET_CONFIG_PATH -----"
echo "SUPERSET_CONFIG_PATH=${SUPERSET_CONFIG_PATH:-<unset>}"
echo "SUPERSET_SECRET_KEY_SET=$([ -n "${SUPERSET_SECRET_KEY:-}" ] && echo yes || echo no)"
echo "SUPERSET_SECRET_KEY_LEN=${#SUPERSET_SECRET_KEY}"
ls -la "${SUPERSET_CONFIG_PATH:-/app/pythonpath/superset_config.py}" 2>&1 || true
log_ndjson "H2" "secret_and_config_path" \
  "{\"config_path\":\"${SUPERSET_CONFIG_PATH:-}\",\"secret_set\":$([ -n "${SUPERSET_SECRET_KEY:-}" ] && echo true || echo false),\"secret_len\":${#SUPERSET_SECRET_KEY}}"

# H1/H3: DB URL + psycopg2
echo "----- H1/H3: DATABASE_URL + psycopg2 -----"
# Не печатаем полный DSN с паролем — только host/db часть после @
_db_safe=$(printf '%s' "${DATABASE_URL:-}" | sed -E 's#://[^@]+@#://***:***@#')
echo "DATABASE_URL_SAFE=${_db_safe:-<unset>}"
python - <<'PY' 2>&1 | tee /tmp/h1_psycopg.txt
import os, json, sys
out = {"psycopg2": False, "sqlalchemy_uri_prefix": None, "error": None}
try:
    import psycopg2  # noqa: F401
    out["psycopg2"] = True
except Exception as e:
    out["error"] = f"psycopg2_import:{type(e).__name__}:{e}"
uri = os.environ.get("DATABASE_URL", "")
if uri.startswith("postgresql://"):
    out["sqlalchemy_uri_prefix"] = "postgresql+psycopg2://"
elif uri:
    out["sqlalchemy_uri_prefix"] = uri.split("://", 1)[0] + "://"
print(json.dumps(out))
sys.exit(0 if out["psycopg2"] else 1)
PY
_h1_rc=$?
log_ndjson "H1" "psycopg2_and_dsn" "$(cat /tmp/h1_psycopg.txt 2>/dev/null || echo '{}')"
echo "H1_PSYCOPG_RC=${_h1_rc}"

# H5: writable home
echo "----- H5: superset_home writable -----"
if touch /app/superset_home/.write_test 2>/dev/null; then
  rm -f /app/superset_home/.write_test
  echo "H5_WRITABLE=yes"
  log_ndjson "H5" "home_writable" '{"writable":true}'
else
  echo "H5_WRITABLE=no"
  log_ndjson "H5" "home_writable" '{"writable":false}'
fi

# H3: try loading config module values (without secrets dump)
echo "----- H3: load superset_config values -----"
python - <<'PY' 2>&1 | tee /tmp/h3_config.txt
import os, json, sys
path = os.environ.get("SUPERSET_CONFIG_PATH", "/app/pythonpath/superset_config.py")
out = {"loaded": False, "has_secret": False, "has_uri": False, "uri_safe": None, "error": None}
try:
    ns = {}
    with open(path, encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, path, "exec"), ns, ns)
    out["loaded"] = True
    sk = ns.get("SECRET_KEY") or ""
    out["has_secret"] = bool(sk) and sk != "CHANGE_ME_TO_A_COMPLEX_RANDOM_SECRET"
    uri = ns.get("SQLALCHEMY_DATABASE_URI") or ""
    out["has_uri"] = bool(uri)
    if "://" in uri:
        # mask credentials
        scheme, rest = uri.split("://", 1)
        if "@" in rest:
            rest = "***:***@" + rest.split("@", 1)[1]
        out["uri_safe"] = f"{scheme}://{rest}"
    else:
        out["uri_safe"] = uri[:40] if uri else None
except Exception as e:
    out["error"] = f"{type(e).__name__}:{e}"
print(json.dumps(out))
PY
log_ndjson "H3" "config_exec" "$(cat /tmp/h3_config.txt 2>/dev/null || echo '{}')"

run_step() {
  _hid="$1"
  _name="$2"
  shift 2
  echo "----- ${_hid}: running ${_name} -----"
  log_ndjson "$_hid" "step_start" "{\"step\":\"${_name}\"}"
  set +e
  "$@"
  _rc=$?
  set -u
  echo "STEP_${_name}_RC=${_rc}"
  log_ndjson "$_hid" "step_done" "{\"step\":\"${_name}\",\"exit_code\":${_rc}}"
  return $_rc
}

run_step "H1" "db_upgrade" superset db upgrade
_rc_upgrade=$?
if [ "$_rc_upgrade" -ne 0 ]; then
  echo "===== FAIL at db upgrade rc=${_rc_upgrade} ====="
  log_ndjson "H1" "init_failed" "{\"failed_at\":\"db_upgrade\",\"exit_code\":${_rc_upgrade}}"
  exit "$_rc_upgrade"
fi

# H4: create-admin (ignore "already exists" as soft success)
run_step "H4" "create_admin" \
  superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname Admin \
    --email admin@kdbl.local \
    --password "${SUPERSET_ADMIN_PASSWORD:-admin}"
_rc_admin=$?
# create-admin часто возвращает 1 если пользователь уже есть — не валим весь init
if [ "$_rc_admin" -ne 0 ]; then
  echo "WARN: create-admin rc=${_rc_admin} (может быть already exists) — продолжаем"
  log_ndjson "H4" "create_admin_nonzero" "{\"exit_code\":${_rc_admin},\"continuing\":true}"
fi

run_step "H1" "superset_init" superset init
_rc_init=$?
if [ "$_rc_init" -ne 0 ]; then
  echo "===== FAIL at superset init rc=${_rc_init} ====="
  log_ndjson "H1" "init_failed" "{\"failed_at\":\"superset_init\",\"exit_code\":${_rc_init}}"
  exit "$_rc_init"
fi

echo "===== KDBL SUPERSET INIT OK ====="
log_ndjson "META" "init_ok" '{"ok":true}'
exit 0
