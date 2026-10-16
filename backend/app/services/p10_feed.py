"""P10 Arete weekly feed: P09 -> P10 split and row generation."""

from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta

from fastapi import HTTPException

from app.services.planning import product_rows_for_account
from app.services.promotions import approved_uplift
from app.utils import future_weeks, week_monday


def largest_remainder(total: int, shares: list[tuple[str, float]]) -> dict[str, int]:
    if not shares:
        return {}
    exact = [(material, total * share / 100) for material, share in shares]
    allocated = {material: int(value) for material, value in exact}
    remainder = total - sum(allocated.values())
    order = sorted(exact, key=lambda pair: pair[1] - int(pair[1]), reverse=True)
    for index in range(remainder):
        allocated[order[index % len(order)][0]] += 1
    return allocated


def build_p10_rows(db: sqlite3.Connection, market_code: str) -> list[dict[str, str]]:
    market = db.execute("SELECT * FROM market WHERE code=?", (market_code,)).fetchone()
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")
    result = []
    weeks = future_weeks(int(market["horizon_weeks"]))
    customers = db.execute(
        "SELECT id,name FROM customer_l04 WHERE market_code=? AND active=1",
        (market_code,),
    )
    for customer in customers:
        products = product_rows_for_account(db, market_code, customer["id"], include_approved=True)
        for product in products:
            for week in weeks:
                base_row = db.execute(
                    "SELECT qty_cs FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week=?",
                    (market_code, customer["id"], product["code"], week),
                ).fetchone()
                base_p09 = math.floor(float(base_row["qty_cs"]) + 0.5) if base_row else 0
                lift_p09 = math.floor(
                    approved_uplift(db, market_code, customer["id"], product["code"], week) + 0.5
                )
                split_rows = db.execute(
                    "SELECT s.material,s.share FROM p09_p10_split s "
                    "JOIN material_p10 m ON m.material=s.material WHERE s.p09_code=? AND m.active=1 "
                    "AND s.valid_from<=? ORDER BY s.valid_from DESC",
                    (product["code"], date.today().isoformat()),
                ).fetchall()
                latest: dict[str, float] = {}
                for split in split_rows:
                    latest.setdefault(split["material"], float(split["share"]))
                shares = list(latest.items())
                if not shares:
                    materials = [
                        r["material"]
                        for r in db.execute(
                            "SELECT material FROM material_p10 WHERE p09_code=? AND active=1",
                            (product["code"],),
                        )
                    ]
                    shares = [(m, 100 / len(materials)) for m in materials] if materials else []
                share_total = sum(share for _, share in shares)
                if shares and abs(share_total - 100) > 0.01:
                    raise HTTPException(
                        status_code=500,
                        detail=f"P10 split shares for {product['code']} sum to {share_total:.2f}%, not 100%",
                    )
                base_split = largest_remainder(base_p09, shares)
                lift_split = largest_remainder(lift_p09, shares)
                monday = week_monday(week)
                sunday = monday + timedelta(days=6)
                for material, _ in shares:
                    base = base_split[material]
                    lift = lift_split[material]
                    result.append(
                        {
                            "Start Date": f"{monday.isoformat()} 00:00:00",
                            "End Date": f"{sunday.isoformat()} 00:00:00",
                            "Plan Account": customer["name"],
                            "Material Number": material,
                            "BaseVolume": str(base),
                            "LiftVolume": str(lift),
                            "TotalVolume": str(base + lift),
                            "PromoNumber": f"00{customer['name']}{material}{monday:%Y%m%d}",
                            "Consumption Start": f"{monday.isoformat()} 00:00:00",
                            "Consumption End": f"{sunday.isoformat()} 00:00:00",
                            "Sales Org": market["p10_sales_org"],
                        }
                    )
    return result


P10_COLUMNS = (
    "Start Date",
    "End Date",
    "Plan Account",
    "Material Number",
    "BaseVolume",
    "LiftVolume",
    "TotalVolume",
    "PromoNumber",
    "Consumption Start",
    "Consumption End",
    "Sales Org",
)
