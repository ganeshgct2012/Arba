"""Date and ISO-week helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso_week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_monday(week: str) -> date:
    try:
        year_text, week_text = week.split("-W", maxsplit=1)
        return date.fromisocalendar(int(year_text), int(week_text), 1)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid ISO week: {week}") from exc


def future_weeks(count: int = 52) -> list[str]:
    current = date.today()
    monday = current - timedelta(days=current.weekday())
    return [iso_week(monday + timedelta(weeks=offset)) for offset in range(count)]


def historical_weeks(count: int = 52) -> list[str]:
    current = date.today()
    monday = current - timedelta(days=current.weekday())
    return [iso_week(monday - timedelta(weeks=offset)) for offset in range(count, 0, -1)]
