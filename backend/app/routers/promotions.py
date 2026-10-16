"""Promotions screen: create/edit and workflow (save, confirm, approve, revert)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, check_assignment, require_role
from app.schemas import PromoPayload
from app.services.audit import audit, log_status
from app.services.promotions import (
    next_promo_number,
    promotion_baseline,
    promotion_json,
)
from app.utils import utcnow

router = APIRouter(tags=['promotions'])


@router.get(f"{API_PREFIX}/promotions/baseline")
async def promotion_baselines(
    market: str,
    customer_id: int,
    start_date: date,
    end_date: date,
    user: CurrentUser,
) -> dict[str, Any]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End Date must be on or after Start Date")
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        rows = db.execute(
            "SELECT p.code FROM listing l JOIN product_p09 p ON p.code=l.p09_code "
            "WHERE l.market_code=? AND l.customer_id=? AND p.active=1 ORDER BY p.description",
            (market, customer_id),
        ).fetchall()
        baselines = {
            row["code"]: promotion_baseline(
                db, market, customer_id, row["code"], start_date, end_date
            )
            for row in rows
        }
    return {"baselines": baselines}


@router.get(f"{API_PREFIX}/promotions")
async def get_promotions(
    user: CurrentUser, market: str | None = None, customer_id: int | None = None
) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        query = "SELECT pr.*,c.name AS customer_name FROM promotion pr JOIN customer_l04 c ON c.id=pr.customer_id WHERE 1=1"
        parameters: list[Any] = []
        if market:
            query += " AND pr.market_code=?"
            parameters.append(market)
        if customer_id:
            query += " AND pr.customer_id=?"
            parameters.append(customer_id)
        if user["role"] != "ADMIN":
            query += " AND EXISTS(SELECT 1 FROM user_assignment ua WHERE ua.user_id=? AND ua.market_code=pr.market_code AND ua.customer_id=pr.customer_id)"
            parameters.append(user["id"])
        rows = db.execute(
            query + " ORDER BY pr.start_date DESC,pr.promo_number DESC", parameters
        ).fetchall()
        promos = [promotion_json(db, row) for row in rows]
    return {"promotions": promos}


@router.post(f"{API_PREFIX}/promotions")
async def save_promotion(payload: PromoPayload, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "PLANNER", "APPROVER")
    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=422, detail="Promotion End Date must be on or after Start Date"
        )
    if payload.cons_end < payload.cons_start:
        raise HTTPException(
            status_code=422,
            detail="Consumption End must be on or after Consumption Start",
        )
    if not payload.items:
        raise HTTPException(status_code=422, detail="Select at least one promotion product")
    with DB_LOCK, connect() as db:
        with db:
            market = db.execute(
                "SELECT plan_mode FROM market WHERE code=?", (payload.market,)
            ).fetchone()
            if market is None:
                raise HTTPException(status_code=404, detail="Market not found")
            check_assignment(db, user, payload.market, payload.customer_id)
            tactic = db.execute(
                "SELECT 1 FROM tactic WHERE market_code=? AND name=? AND active=1",
                (payload.market, payload.tactic),
            ).fetchone()
            if not tactic:
                raise HTTPException(
                    status_code=422, detail="Tactic is not configured for this market"
                )
            listed = {
                r["p09_code"]
                for r in db.execute(
                    "SELECT p09_code FROM listing WHERE market_code=? AND customer_id=?",
                    (payload.market, payload.customer_id),
                )
            }
            if not set(payload.items).issubset(listed):
                raise HTTPException(
                    status_code=400,
                    detail="Every promotion product must be listed for this account",
                )
            for product, total in payload.items.items():
                if not math.isfinite(total) or total < 0:
                    raise HTTPException(status_code=422, detail="Item totals must be non-negative")
                baseline = promotion_baseline(
                    db,
                    payload.market,
                    payload.customer_id,
                    product,
                    payload.start_date,
                    payload.end_date,
                )
                if total < baseline:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Total cases for {product} must be at least its baseline ({baseline:g})",
                    )

            if payload.id is None:
                promo_number = next_promo_number(db)
                cursor = db.execute(
                    "INSERT INTO promotion(promo_number,market_code,customer_id,start_date,end_date,cons_start,cons_end,"
                    "tactic,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        promo_number,
                        payload.market,
                        payload.customer_id,
                        payload.start_date.isoformat(),
                        payload.end_date.isoformat(),
                        payload.cons_start.isoformat(),
                        payload.cons_end.isoformat(),
                        payload.tactic,
                        "NEW",
                        user["email"],
                        utcnow().isoformat(),
                    ),
                )
                promo_id = int(cursor.lastrowid)
                log_status(db, promo_id, user["email"], None, "NEW")
                old_status = "NEW"
            else:
                row = db.execute("SELECT * FROM promotion WHERE id=?", (payload.id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Promotion not found")
                check_assignment(db, user, row["market_code"], int(row["customer_id"]))
                if row["status"] not in {"NEW", "SAVED"}:
                    raise HTTPException(
                        status_code=409,
                        detail="Only Entry or Planned promotions can be edited; revert an approved promotion first.",
                    )
                if payload.version is None or payload.version != row["version"]:
                    raise HTTPException(
                        status_code=409,
                        detail="Promotion was changed by another user. Reload before saving.",
                    )
                promo_id = int(row["id"])
                old_status = row["status"]
                cursor = db.execute(
                    "UPDATE promotion SET market_code=?,customer_id=?,start_date=?,end_date=?,cons_start=?,cons_end=?,"
                    "tactic=?,version=version+1 WHERE id=? AND version=?",
                    (
                        payload.market,
                        payload.customer_id,
                        payload.start_date.isoformat(),
                        payload.end_date.isoformat(),
                        payload.cons_start.isoformat(),
                        payload.cons_end.isoformat(),
                        payload.tactic,
                        promo_id,
                        row["version"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise HTTPException(
                        status_code=409, detail="Promotion was changed by another user"
                    )
            warnings = db.execute(
                "SELECT DISTINCT pr.promo_number FROM promotion pr JOIN promotion_item pi ON pi.promotion_id=pr.id "
                "WHERE pr.market_code=? AND pr.customer_id=? AND pr.id<>? "
                "AND pr.start_date<=? AND pr.end_date>=? AND pi.p09_code IN ({})".format(
                    ",".join("?" for _ in payload.items)
                ),
                (
                    payload.market,
                    payload.customer_id,
                    promo_id,
                    payload.end_date.isoformat(),
                    payload.start_date.isoformat(),
                    *payload.items.keys(),
                ),
            ).fetchall()
            db.execute("DELETE FROM promotion_item WHERE promotion_id=?", (promo_id,))
            db.executemany(
                "INSERT INTO promotion_item(promotion_id,p09_code,total_cs) VALUES(?,?,?)",
                [(promo_id, product, total) for product, total in payload.items.items()],
            )
            audit(
                db,
                "promotion",
                str(promo_id),
                "CREATE_ENTRY" if payload.id is None else "EDIT",
                user["email"],
                before={"status": old_status},
                after={
                    "status": "NEW" if payload.id is None else old_status,
                    "products": list(payload.items),
                },
            )
            result = promotion_json(
                db,
                db.execute("SELECT * FROM promotion WHERE id=?", (promo_id,)).fetchone(),
            )
    return {
        "promotion": result,
        "overlap_warnings": [r["promo_number"] for r in warnings],
    }


@router.post(f"{API_PREFIX}/promotions/{{promotion_id}}/save")
async def plan_promotion(promotion_id: int, user: CurrentUser) -> dict[str, str]:
    require_role(user, "PLANNER", "APPROVER")
    with DB_LOCK, connect() as db:
        with db:
            row = db.execute("SELECT * FROM promotion WHERE id=?", (promotion_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Promotion not found")
            check_assignment(db, user, row["market_code"], row["customer_id"])
            if row["status"] != "NEW":
                raise HTTPException(status_code=409, detail="Only Entry promotions can be saved as Planned")
            db.execute(
                "UPDATE promotion SET status='SAVED',version=version+1 WHERE id=? AND status='NEW'",
                (promotion_id,),
            )
            log_status(db, promotion_id, user["email"], "NEW", "SAVED")
            audit(
                db,
                "promotion",
                str(promotion_id),
                "SAVE",
                user["email"],
                before={"status": "NEW"},
                after={"status": "SAVED"},
            )
    return {"status": "SAVED"}


@router.post(f"{API_PREFIX}/promotions/{{promotion_id}}/confirm")
async def confirm_promotion(promotion_id: int, user: CurrentUser) -> dict[str, str]:
    require_role(user, "PLANNER", "APPROVER")
    with DB_LOCK, connect() as db:
        with db:
            row = db.execute("SELECT * FROM promotion WHERE id=?", (promotion_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Promotion not found")
            check_assignment(db, user, row["market_code"], row["customer_id"])
            if row["status"] != "SAVED":
                raise HTTPException(status_code=409, detail="Only Planned promotions can be confirmed")
            db.execute(
                "UPDATE promotion SET status='CHANGED',version=version+1 WHERE id=? AND status='SAVED'",
                (promotion_id,),
            )
            log_status(db, promotion_id, user["email"], "SAVED", "CHANGED")
            audit(
                db,
                "promotion",
                str(promotion_id),
                "CONFIRM",
                user["email"],
                before={"status": "SAVED"},
                after={"status": "CHANGED"},
            )
    return {"status": "CHANGED"}


@router.post(f"{API_PREFIX}/promotions/{{promotion_id}}/approve")
async def approve_promotion(promotion_id: int, user: CurrentUser) -> dict[str, str]:
    require_role(user, "APPROVER")
    with DB_LOCK, connect() as db:
        with db:
            row = db.execute("SELECT * FROM promotion WHERE id=?", (promotion_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Promotion not found")
            check_assignment(db, user, row["market_code"], row["customer_id"])
            if row["status"] != "CHANGED":
                raise HTTPException(status_code=409, detail="Only Approval Pending promotions can be approved")
            db.execute(
                "UPDATE promotion SET status='APPROVED',approved_by=?,approved_at=?,version=version+1 "
                "WHERE id=? AND status='CHANGED'",
                (user["email"], utcnow().isoformat(), promotion_id),
            )
            log_status(db, promotion_id, user["email"], "CHANGED", "APPROVED")
            audit(
                db,
                "promotion",
                str(promotion_id),
                "APPROVE",
                user["email"],
                before={"status": "CHANGED"},
                after={"status": "APPROVED"},
            )
    return {"status": "APPROVED"}


@router.post(f"{API_PREFIX}/promotions/{{promotion_id}}/revert")
async def revert_promotion(promotion_id: int, user: CurrentUser) -> dict[str, str]:
    require_role(user, "PLANNER", "APPROVER")
    with DB_LOCK, connect() as db:
        with db:
            row = db.execute("SELECT * FROM promotion WHERE id=?", (promotion_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Promotion not found")
            check_assignment(db, user, row["market_code"], row["customer_id"])
            if row["status"] != "APPROVED" or date.fromisoformat(row["start_date"]) <= date.today():
                raise HTTPException(
                    status_code=409,
                    detail="Only future APPROVED promotions can be reverted",
                )
            db.execute(
                "UPDATE promotion SET status='SAVED',approved_by=NULL,approved_at=NULL,version=version+1 WHERE id=?",
                (promotion_id,),
            )
            log_status(db, promotion_id, user["email"], "APPROVED", "SAVED")
            audit(
                db,
                "promotion",
                str(promotion_id),
                "REVERT",
                user["email"],
                before={"status": "APPROVED"},
                after={"status": "SAVED"},
            )
    return {"status": "SAVED"}
