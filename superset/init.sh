#!/bin/sh
# Инициализация Apache Superset: миграции, admin, roles.
set -eu

echo "===== KDBL SUPERSET INIT START ====="

echo "-> superset db upgrade"
superset db upgrade

echo "-> create-admin (ignore if already exists)"
set +e
superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname Admin \
  --email admin@kdbl.local \
  --password "${SUPERSET_ADMIN_PASSWORD:-admin}"
_admin_rc=$?
set -e
if [ "$_admin_rc" -ne 0 ]; then
  echo "WARN: create-admin exited ${_admin_rc} (often 'already exists') — continuing"
fi

echo "-> superset init"
superset init

echo "===== KDBL SUPERSET INIT OK ====="
