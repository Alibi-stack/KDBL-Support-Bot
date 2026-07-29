"""
superset_config.py -- конфигурация Apache Superset для KDBL-Support-Bot.

Метаданные Superset (дашборды, пользователи) хранятся в SQLite внутри
volume superset_home -- так рекомендует MVP-план: Postgres `support`
подключается потом через UI как datasource
(Add Database -> postgresql://kdbl:***@postgres:5432/support).

Официальный образ apache/superset:latest (lean) НЕ включает psycopg2.
Поэтому SQLALCHEMY_DATABASE_URI нельзя насильно ставить на Postgres
без отдельной установки драйвера -- иначе `superset db upgrade` падает
с exit 1 (ModuleNotFoundError: psycopg2).
"""

import os

# Достаточно длинный ключ, отличный от CHANGE_ME_TO_A_COMPLEX_RANDOM_SECRET,
# иначе Superset откажется стартовать.
SECRET_KEY = os.environ.get(
    "SUPERSET_SECRET_KEY",
    "kdbl-superset-dev-secret-change-me-in-production-please-32b",
)

# Явно оставляем metadata на SQLite в SUPERSET_HOME (дефолт образа).
# Не переопределяем SQLALCHEMY_DATABASE_URI.
