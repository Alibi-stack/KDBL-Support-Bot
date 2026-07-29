# Обёртка над официальным lean-образом: добавляем psycopg2, чтобы в UI
# можно было подключить Postgres `support` как datasource.
FROM apache/superset:latest

USER root
RUN pip install --no-cache-dir "psycopg2-binary>=2.9,<3.0"
USER superset
