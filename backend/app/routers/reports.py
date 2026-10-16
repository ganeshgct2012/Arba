"""Sales History, Volume Report and Promo Calendar screens."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, check_assignment
from app.services.planning import product_rows_for_account
from app.services.promotions import approved_uplift
from app.utils import future_weeks, historical_weeks, iso_week, week_monday

router = APIRouter(tags=['reports'])


@router.get(f"{API_PREFIX}/history")
async def sales_history(market: str, customer_id: int, user: CurrentUser) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        products = product_rows_for_account(db, market, customer_id, include_approved=False)
        weeks = historical_weeks()
        result = []
        for product in products:
            lookup = {
                r["iso_week"]: r["qty_cs"]
                for r in db.execute(
                    "SELECT iso_week,qty_cs FROM actual_sellin WHERE market_code=? AND customer_id=? AND p09_code=?",
                    (market, customer_id, product["code"]),
                )
            }
            result.append({**dict(product), "values": [lookup.get(w, 0) for w in weeks]})
    return {"weeks": weeks, "products": result}


@router.get(f"{API_PREFIX}/report")
async def volume_report(
    user: CurrentUser, market: str, year: int, customer_id: int | None = None
) -> dict[str, Any]:
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100")
    with DB_LOCK, connect() as db:
        market_row = db.execute("SELECT plan_mode FROM market WHERE code=?", (market,)).fetchone()
        if not market_row:
            raise HTTPException(status_code=404, detail="Market not found")
        if customer_id:
            check_assignment(db, user, market, customer_id)
        else:
            assigned = {
                r["customer_id"]
                for r in db.execute(
                    "SELECT customer_id FROM user_assignment WHERE user_id=? AND market_code=?",
                    (user["id"], market),
                )
            }
            if user["role"] != "ADMIN" and not assigned:
                raise HTTPException(status_code=403, detail="Market is not assigned")
        params: list[Any] = [market]
        query = "SELECT id,name FROM customer_l04 WHERE market_code=? AND active=1"
        if customer_id:
            query += " AND id=?"
            params.append(customer_id)
        elif user["role"] != "ADMIN":
            marks = ",".join("?" for _ in assigned)
            query += f" AND id IN ({marks})"
            params.extend(sorted(assigned))
        customers = db.execute(query, params).fetchall()
        results = []
        for customer in customers:
            products = product_rows_for_account(db, market, customer["id"], include_approved=True)
            for product in products:
                months = [0.0] * 12
                for week in future_weeks(52) + historical_weeks(52):
                    monday = week_monday(week)
                    thursday = monday + timedelta(days=3)
                    if thursday.year != year:
                        continue
                    actual = db.execute(
                        "SELECT qty_cs FROM actual_sellin WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week=?",
                        (market, customer["id"], product["code"], week),
                    ).fetchone()
                    if monday < date.today() - timedelta(days=date.today().weekday()):
                        qty = float(actual["qty_cs"]) if actual else 0
                    else:
                        base = db.execute(
                            "SELECT qty_cs FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week=?",
                            (market, customer["id"], product["code"], week),
                        ).fetchone()
                        qty = float(base["qty_cs"]) if base else 0
                        if market_row["plan_mode"] == "PROMO":
                            qty += approved_uplift(
                                db, market, customer["id"], product["code"], week
                            )
                    months[thursday.month - 1] += qty
                results.append(
                    {
                        "customer": customer["name"],
                        "customer_id": customer["id"],
                        "product": product["code"],
                        "description": product["description"],
                        "brand": product["brand"],
                        "months": months,
                        "total": sum(months),
                    }
                )
    return {
        "year": year,
        "market": market,
        "rows": results,
        "month_names": [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
    }


@router.get(f"{API_PREFIX}/calendar")
async def promo_calendar(market: str, customer_id: int, user: CurrentUser) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        market_row = db.execute(
            "SELECT horizon_weeks FROM market WHERE code=? AND active=1", (market,)
        ).fetchone()
        if market_row is None:
            raise HTTPException(status_code=404, detail="Market not found")
        rows = db.execute(
            "SELECT pr.id,pr.promo_number,pr.start_date,pr.end_date,pr.tactic,pr.status,"
            "c.name AS customer_name,p.sub_brand,COUNT(DISTINCT pi.p09_code) AS product_count "
            "FROM promotion pr JOIN promotion_item pi ON pi.promotion_id=pr.id "
            "JOIN product_p09 p ON p.code=pi.p09_code "
            "JOIN customer_l04 c ON c.id=pr.customer_id "
            "WHERE pr.market_code=? AND pr.customer_id=? AND pr.status IN ('SAVED','CHANGED','APPROVED') "
            "GROUP BY pr.id,p.sub_brand "
            "ORDER BY pr.start_date,pr.promo_number,p.sub_brand",
            (market, customer_id),
        ).fetchall()
        promotions = [dict(row) for row in rows]
        weeks = future_weeks(int(market_row["horizon_weeks"]))
    first_week = week_monday(weeks[0])
    last_week = week_monday(weeks[-1])
    if promotions:
        first_week = min(
            first_week,
            min(week_monday(iso_week(date.fromisoformat(row["start_date"]))) for row in promotions),
        )
        last_week = max(
            last_week,
            max(week_monday(iso_week(date.fromisoformat(row["end_date"]))) for row in promotions),
        )
    calendar_weeks = []
    week = first_week
    while week <= last_week:
        calendar_weeks.append(iso_week(week))
        week += timedelta(weeks=1)
    return {"weeks": calendar_weeks, "promotions": promotions}
