from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile
from openpyxl import Workbook

from config import get_settings
from services.ticket_storage import (
    get_app_state,
    get_tickets_for_period,
    set_app_state,
)

REPORT_STATE_KEY = "last_daily_report_date"
logger = logging.getLogger(__name__)


async def daily_report_loop(bot: Bot) -> None:
    while True:
        try:
            await maybe_send_daily_report(bot)
        except Exception:
            logger.exception("Cannot send daily ticket report")
        await asyncio.sleep(60)


async def maybe_send_daily_report(bot: Bot) -> None:
    settings = get_settings()
    if settings.admin_chat_id is None:
        return

    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    if now.hour < settings.report_hour:
        return

    report_date = now.date()
    last_report_date = await get_app_state(REPORT_STATE_KEY)
    if last_report_date == report_date.isoformat():
        return

    report_path = await build_daily_ticket_report(report_date)
    await bot.send_document(
        settings.admin_chat_id,
        FSInputFile(report_path),
        caption=f"Ежедневный отчёт по обращениям за {report_date:%d.%m.%Y}",
    )
    await set_app_state(REPORT_STATE_KEY, report_date.isoformat())


async def build_daily_ticket_report(report_date: date) -> Path:
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    start_local = datetime.combine(report_date, time.min, tzinfo=tz)
    end_local = datetime.combine(report_date, time.max, tzinfo=tz)
    start_utc = start_local.astimezone(UTC).isoformat(timespec="seconds")
    end_utc = end_local.astimezone(UTC).isoformat(timespec="seconds")

    tickets = await get_tickets_for_period(start_utc, end_utc)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tickets"
    sheet.append(
        [
            "Ticket ID",
            "User ID",
            "User",
            "Username",
            "Question",
            "Status",
            "Operator",
            "Created",
            "Updated",
            "Closed",
        ]
    )
    for ticket in tickets:
        sheet.append(
            [
                ticket.id,
                ticket.user_id,
                ticket.user_name,
                f"@{ticket.username}" if ticket.username else "",
                ticket.question,
                ticket.status,
                ticket.operator_name or "",
                format_report_datetime(ticket.created_at, tz),
                format_report_datetime(ticket.updated_at, tz),
                format_report_datetime(ticket.closed_at, tz),
            ]
        )

    summary = workbook.create_sheet("Summary")
    summary.append(["Дата", report_date.isoformat()])
    summary.append(["Всего тикетов", len(tickets)])
    summary.append(["Открытые", sum(1 for ticket in tickets if ticket.status == "open")])
    summary.append(
        ["В работе", sum(1 for ticket in tickets if ticket.status == "in_progress")]
    )
    summary.append(["Закрытые", sum(1 for ticket in tickets if ticket.status == "closed")])

    for worksheet in workbook.worksheets:
        for column in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            worksheet.column_dimensions[column[0].column_letter].width = min(
                max(max_length + 2, 12),
                60,
            )

    report_dir = Path(tempfile.gettempdir()) / "kdbl_support_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"tickets_{report_date.isoformat()}.xlsx"
    workbook.save(report_path)
    return report_path


def format_report_datetime(value: str | None, tz: ZoneInfo) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(tz).strftime("%d.%m.%Y %H:%M")
