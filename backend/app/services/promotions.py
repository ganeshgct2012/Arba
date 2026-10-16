"""Promotion calculations: baseline over promo weeks, uplift, JSON shape."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

from app.utils import iso_week, week_monday


def promotion_baseline(
    db: sqlite3.Connection,
    market: str,
    customer_id: int,
    product: str,
    start: date,
    end: date,
) -> float:
    cursor = start - timedelta(days=start.weekday())
    final = end - timedelta(days=end.weekday())
    total = 0.0
    while cursor <= final:
        week = iso_week(cursor)
        row = db.execute(
            "SELECT qty_cs FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week=?",
            (market, customer_id, product, week),
        ).fetchone()
        total += float(row["qty_cs"]) if row else 0.0
        cursor += timedelta(weeks=1)
    return total


def promotion_json(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    items = []
    for item in db.execute(
        "SELECT pi.p09_code,pi.total_cs,p.description FROM promotion_item pi "
        "JOIN product_p09 p ON p.code=pi.p09_code WHERE pi.promotion_id=? ORDER BY p.description",
        (row["id"],),
    ):
        baseline = promotion_baseline(
            db,
            row["market_code"],
            row["customer_id"],
            item["p09_code"],
            date.fromisoformat(row["start_date"]),
            date.fromisoformat(row["end_date"]),
        )
        total = float(item["total_cs"])
        actual = 0.0
        if date.fromisoformat(row["end_date"]) < date.today():
            actual = float(
                db.execute(
                    "SELECT COALESCE(SUM(qty_cs),0) AS q FROM actual_sellin "
                    "WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week BETWEEN ? AND ?",
                    (
                        row["market_code"],
                        row["customer_id"],
                        item["p09_code"],
                        iso_week(date.fromisoformat(row["start_date"])),
                        iso_week(date.fromisoformat(row["end_date"])),
                    ),
                ).fetchone()["q"]
            )
        items.append(
            {
                "product": item["p09_code"],
                "description": item["description"],
                "baseline": baseline,
                "total": total,
                "uplift": total - baseline,
                "actual": actual,
            }
        )
    return {
        **dict(row),
        "items": items,
        "baseline": sum(i["baseline"] for i in items),
        "total": sum(i["total"] for i in items),
        "uplift": sum(i["uplift"] for i in items),
        "actual": sum(i["actual"] for i in items),
    }


def next_promo_number(db: sqlite3.Connection) -> str:
    row = db.execute(
        "SELECT MAX(CAST(SUBSTR(promo_number,3) AS INTEGER)) AS n FROM promotion"
    ).fetchone()
    return f"PR{(int(row['n'] or 0) + 1):06d}"


def approved_uplift(
    db: sqlite3.Connection, market: str, customer: int, product: str, week: str
) -> float:
    monday = week_monday(week)
    sunday = monday + timedelta(days=6)
    total = 0.0
    rows = db.execute(
        "SELECT pr.start_date,pr.end_date,pi.total_cs FROM promotion pr "
        "JOIN promotion_item pi ON pi.promotion_id=pr.id "
        "WHERE pr.market_code=? AND pr.customer_id=? AND pr.status='APPROVED' AND pi.p09_code=? "
        "AND pr.start_date<=? AND pr.end_date>=?",
        (market, customer, product, sunday.isoformat(), monday.isoformat()),
    )
    for row in rows:
        start = date.fromisoformat(row["start_date"])
        end = date.fromisoformat(row["end_date"])
        weeks = max(
            1,
            ((end - timedelta(days=end.weekday())) - (start - timedelta(days=start.weekday()))).days
            // 7
            + 1,
        )
        base = promotion_baseline(db, market, customer, product, start, end)
        total += max(0.0, float(row["total_cs"]) - base) / weeks
    return total
