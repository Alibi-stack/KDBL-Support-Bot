# Обёртка над официальным lean-образом apache/superset:latest.
# С 5.x пакеты ставятся через uv в /app/.venv; обычный pip (и даже
# /app/.venv/bin/pip без uv) может не попасть в то окружение, которое
# использует gunicorn -- UI тогда пишет
# "Could not load database driver for: postgresql".
# Официальный рецепт: https://superset.apache.org/docs/installation/docker-builds
FROM apache/superset:latest

USER root
RUN . /app/.venv/bin/activate \
    && uv pip install --no-cache "psycopg2-binary>=2.9,<3.0" \
    && python -c "import psycopg2; print('psycopg2 OK', psycopg2.__version__)"
USER superset
