"""Background scheduler: pipeline schedules and inactive-user deactivation."""

from __future__ import annotations

import asyncio
import calendar
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import logger
from app.db import DB_LOCK, connect
from app.services.audit import audit
from app.services.pipeline_runner import execute_pipeline
from app.utils import utcnow


def schedule_due(pipeline: sqlite3.Row, now: datetime) -> tuple[bool, str]:
    try:
        zone = ZoneInfo(str(pipeline["schedule_timezone"]))
    except ZoneInfoNotFoundError as exc:
        logger.error("Invalid timezone for pipeline %s", pipeline["id"])
        raise ValueError(f"Unknown timezone: {pipeline['schedule_timezone']}") from exc
    local_now = now.astimezone(zone)
    if pipeline["schedule_start_date"] and local_now.date() < date.fromisoformat(pipeline["schedule_start_date"]):
        return False, f"not-started:{local_now.date()}"
    if pipeline["schedule_end_date"] and local_now.date() > date.fromisoformat(pipeline["schedule_end_date"]):
        return False, f"ended:{local_now.date()}"
    run_hour, run_minute = map(int, str(pipeline["schedule_time"]).split(":"))
    due = local_now.hour == run_hour and local_now.minute == run_minute
    frequency = pipeline["schedule_frequency"]
    if frequency == "WEEKLY":
        due = due and local_now.weekday() == int(pipeline["schedule_weekday"])
    elif frequency == "MONTHLY":
        due = due and local_now.day == min(
            int(pipeline["schedule_month_day"]),
            calendar.monthrange(local_now.year, local_now.month)[1],
        )
    elif frequency == "QUARTERLY":
        due = (
            due
            and (local_now.month - 1) % 3 + 1 == int(pipeline["schedule_quarter_month"])
            and local_now.day
            == min(
                int(pipeline["schedule_month_day"]),
                calendar.monthrange(local_now.year, local_now.month)[1],
            )
        )
    elif frequency != "DAILY":
        raise ValueError(f"Unknown pipeline schedule frequency: {frequency}")
    return due, f"{frequency}:{local_now:%Y-%m-%dT%H:%M}"


def next_pipeline_run(pipeline: sqlite3.Row, now: datetime | None = None) -> str | None:
    if not pipeline["enabled"]:
        return None
    try:
        zone = ZoneInfo(str(pipeline["schedule_timezone"]))
        local_now = (now or utcnow()).astimezone(zone)
        run_hour, run_minute = map(int, str(pipeline["schedule_time"]).split(":"))
        frequency = str(pipeline["schedule_frequency"])
        start_date = (
            date.fromisoformat(pipeline["schedule_start_date"])
            if pipeline["schedule_start_date"]
            else None
        )
        end_date = (
            date.fromisoformat(pipeline["schedule_end_date"])
            if pipeline["schedule_end_date"]
            else None
        )
        first_day = max(local_now.date(), start_date) if start_date else local_now.date()
        for offset in range(370):
            day = first_day + timedelta(days=offset)
            if end_date and day > end_date:
                return None
            if frequency == "WEEKLY" and day.weekday() != int(pipeline["schedule_weekday"]):
                continue
            if frequency == "MONTHLY":
                if day.day != min(
                    int(pipeline["schedule_month_day"]),
                    calendar.monthrange(day.year, day.month)[1],
                ):
                    continue
            elif frequency == "QUARTERLY":
                if (day.month - 1) % 3 + 1 != int(pipeline["schedule_quarter_month"]):
                    continue
                if day.day != min(
                    int(pipeline["schedule_month_day"]),
                    calendar.monthrange(day.year, day.month)[1],
                ):
                    continue
            elif frequency not in {"DAILY", "WEEKLY", "MONTHLY"}:
                return None
            candidate = datetime(
                day.year, day.month, day.day, run_hour, run_minute, tzinfo=zone
            )
            if candidate > local_now:
                return candidate.isoformat()
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return None


async def pipeline_scheduler() -> None:
    while True:
        try:
            scheduled: list[str] = []
            now = utcnow()
            with DB_LOCK, connect() as db:
                inactive_before = (now - timedelta(days=30)).isoformat()
                inactive_users = db.execute(
                    "SELECT id,email,last_login_at FROM app_user "
                    "WHERE active=1 AND last_login_at IS NOT NULL AND last_login_at<?",
                    (inactive_before,),
                ).fetchall()
                if inactive_users:
                    with db:
                        for inactive_user in inactive_users:
                            db.execute(
                                "UPDATE app_user SET active=0 WHERE id=? AND active=1",
                                (inactive_user["id"],),
                            )
                            if db.execute("SELECT changes()").fetchone()[0]:
                                audit(
                                    db,
                                    "app_user",
                                    str(inactive_user["id"]),
                                    "AUTO_DEACTIVATE_INACTIVE",
                                    "scheduler@arba.local",
                                    before={"active": True, "last_login_at": inactive_user["last_login_at"]},
                                    after={"active": False},
                                )
                for row in db.execute("SELECT * FROM pipeline WHERE enabled=1"):
                    try:
                        due, schedule_key = schedule_due(row, now)
                    except ValueError:
                        continue
                    if due and row["last_schedule_key"] != schedule_key:
                        with db:
                            db.execute(
                                "UPDATE pipeline SET last_schedule_key=? "
                                "WHERE id=? AND (last_schedule_key IS NULL OR last_schedule_key<>?)",
                                (schedule_key, row["id"], schedule_key),
                            )
                            if db.execute("SELECT changes()").fetchone()[0]:
                                scheduled.append(str(row["id"]))
            for pipeline_id in scheduled:
                try:
                    await execute_pipeline(
                        pipeline_id,
                        {"id": 0, "role": "ADMIN", "email": "scheduler@arba.local"},
                        dry_run=False,
                        trigger="SCHEDULE",
                    )
                except Exception:
                    logger.exception("Scheduled pipeline %s failed to run", pipeline_id)
        except sqlite3.Error:
            logger.exception("Pipeline scheduler database error")
        await asyncio.sleep(20)
