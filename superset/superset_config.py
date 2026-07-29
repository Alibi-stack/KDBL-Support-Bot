"""
superset_config.py -- конфигурация Apache Superset для KDBL-Support-Bot.

Монтируется в контейнер по SUPERSET_CONFIG_PATH=/app/pythonpath/superset_config.py
(см. docker-compose.yml, сервисы superset-init и superset).

Superset использует ту же Postgres-БД (support), что и бот -- переменная
DATABASE_URL общая для всего стека (.env). После первого старта в самом
Superset можно дополнительно добавить "support" как Database-источник
для дашбордов (Settings -> Database Connections -> + Database).
"""

import os

_database_url = os.environ.get("DATABASE_URL", "postgresql://kdbl:kdbl@postgres:5432/support")

# asyncpg-совместимый DSN (postgresql://...) бота нужно превратить в
# SQLAlchemy/psycopg2-совместимый (postgresql+psycopg2://...) для Superset.
SQLALCHEMY_DATABASE_URI = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

SECRET_KEY = os.environ.get(
    "SUPERSET_SECRET_KEY",
    "change_me_to_a_long_random_string_please",
)
