"""Product Listing screen."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, check_assignment, require_role
from app.schemas import ListingPayload
from app.services.audit import audit
from app.utils import iso_week, utcnow

router = APIRouter(tags=['listing'])


@router.get(f"{API_PREFIX}/listing")
async def get_listing(market: str, customer_id: int, user: CurrentUser) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        selected = [
            r["p09_code"]
            for r in db.execute(
                "SELECT p09_code FROM listing WHERE market_code=? AND customer_id=?",
                (market, customer_id),
            )
        ]
        products = [
            dict(r)
            for r in db.execute(
                "SELECT code,description,brand,sub_brand,category FROM product_p09 ORDER BY brand,description"
            )
        ]
    return {"selected": selected, "products": products}


@router.put(f"{API_PREFIX}/listing")
async def save_listing(payload: ListingPayload, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "PLANNER")
    with DB_LOCK, connect() as db:
        with db:
            check_assignment(db, user, payload.market, payload.customer_id)
            valid = {r["code"] for r in db.execute("SELECT code FROM product_p09 WHERE active=1")}
            if not set(payload.products).issubset(valid):
                raise HTTPException(status_code=422, detail="Unknown product in listing")
            current = {
                r["p09_code"]
                for r in db.execute(
                    "SELECT p09_code FROM listing WHERE market_code=? AND customer_id=?",
                    (payload.market, payload.customer_id),
                )
            }
            removed = current - set(payload.products)
            warnings = []
            for product in removed:
                future_base = db.execute(
                    "SELECT 1 FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=? AND iso_week>=? LIMIT 1",
                    (
                        payload.market,
                        payload.customer_id,
                        product,
                        iso_week(date.today()),
                    ),
                ).fetchone()
                approved = db.execute(
                    "SELECT 1 FROM promotion_item pi JOIN promotion pr ON pr.id=pi.promotion_id WHERE pr.market_code=? AND pr.customer_id=? AND pi.p09_code=? AND pr.status='APPROVED' AND pr.start_date>? LIMIT 1",
                    (
                        payload.market,
                        payload.customer_id,
                        product,
                        date.today().isoformat(),
                    ),
                ).fetchone()
                if future_base or approved:
                    warnings.append(product)
            db.execute(
                "DELETE FROM listing WHERE market_code=? AND customer_id=?",
                (payload.market, payload.customer_id),
            )
            db.executemany(
                "INSERT INTO listing(market_code,customer_id,p09_code,created_by,created_at) VALUES(?,?,?,?,?)",
                [
                    (
                        payload.market,
                        payload.customer_id,
                        p,
                        user["email"],
                        utcnow().isoformat(),
                    )
                    for p in payload.products
                ],
            )
            audit(
                db,
                "listing",
                f"{payload.market}:{payload.customer_id}",
                "REPLACE",
                user["email"],
                before=sorted(current),
                after=sorted(payload.products),
            )
    return {"saved": len(payload.products), "delisted_with_plans": warnings}
