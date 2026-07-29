"""
render_config.py -- генерирует alertmanager.yml на старте сервиса
alertmanager-init (см. docker-compose.yml).

Мы не храним готовый alertmanager.yml с токеном бота в репозитории (это
секрет) -- вместо этого читаем нужные значения из переменных окружения
(.env, передаётся через env_file) и рендерим итоговый конфиг в volume
alertmanager_config, который потом монтируется read-only в основной
контейнер alertmanager.

Нужные переменные:
    BOT_TOKEN        -- тот же токен, что использует сам бот.
    ALERT_CHAT_ID    -- куда слать алерты (по умолчанию = ADMIN_CHAT_ID,
                        операторская группа).
    ALERT_THREAD_ID  -- id темы "Alerts" внутри этой группы (опционально;
                        если не задан, алерты идут в общий поток группы).

Требует Alertmanager >= 0.28.0 (в этой версии появилась поддержка
message_thread_id для Telegram-получателя).
"""

import os
import sys

from services.env_crypto import decrypt_env_value

OUTPUT_PATH = "/etc/alertmanager/alertmanager.yml"


def main() -> None:
    secret_key = os.environ.get("ENV_SECRET_KEY", "").strip()
    bot_token = str(
        decrypt_env_value(os.environ.get("BOT_TOKEN", "").strip(), secret_key)
    ).strip()
    chat_id = (os.environ.get("ALERT_CHAT_ID") or os.environ.get("ADMIN_CHAT_ID") or "").strip()
    thread_id = os.environ.get("ALERT_THREAD_ID", "").strip()

    if not bot_token or not chat_id:
        print(
            "BOT_TOKEN / ALERT_CHAT_ID (или ADMIN_CHAT_ID) не заданы в .env -- "
            "алерты в Telegram не будут доставляться, пока их не заполнить.",
            file=sys.stderr,
        )

    thread_line = f"\n        message_thread_id: {thread_id}" if thread_id else ""

    config = f"""\
route:
  receiver: telegram-alerts
  group_by: ['alertname']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: telegram-alerts
    telegram_configs:
      - bot_token: '{bot_token}'
        chat_id: {chat_id or 0}{thread_line}
        send_resolved: false
        parse_mode: 'HTML'
        message: |-
          {{{{- range .Alerts }}}}
          🚨 <b>{{{{ .Labels.alertname }}}}</b>
          Статус: {{{{ .Status }}}}
          Важность: {{{{ .Labels.severity }}}}
          {{{{- if .Annotations.summary }}}}
          Кратко: {{{{ .Annotations.summary }}}}
          {{{{- end }}}}
          {{{{- if .Annotations.description }}}}
          Описание: {{{{ .Annotations.description }}}}
          {{{{- end }}}}
          {{{{- end }}}}
"""

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(config)
    print(f"alertmanager.yml сгенерирован: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
