"""FastAPI dependencies: current user and authorisation checks."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.db import DB_LOCK, connect
from app.security import verify_session


def get_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get("arba_session")
    session = verify_session(token) if token else None
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    user_id, _ = session
    with DB_LOCK, connect() as db:
        row = db.execute(
            "SELECT id,email,name,role,active FROM app_user WHERE id=?", (user_id,)
        ).fetchone()
        admin_sales_org_access = [
            item["sales_org"]
            for item in db.execute(
                "SELECT sales_org FROM user_sales_org_admin WHERE user_id=? ORDER BY sales_org",
                (user_id,),
            )
        ]
    if row is None or not row["active"]:
        raise HTTPException(status_code=401, detail="Account is inactive")
    return {**dict(row), "admin_sales_org_access": admin_sales_org_access}


CurrentUser = Annotated[dict[str, Any], Depends(get_user)]


def require_role(user: dict[str, Any], *roles: str) -> None:
    if user["role"] != "ADMIN" and user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Your role cannot perform this action")


def require_access_administrator(user: dict[str, Any]) -> None:
    if user["role"] != "ADMIN" and not user.get("admin_sales_org_access"):
        raise HTTPException(status_code=403, detail="Sales organization administrator access is required")


def check_assignment(
    db: sqlite3.Connection, user: dict[str, Any], market: str, customer: int
) -> None:
    if user["role"] == "ADMIN":
        return
    market_row = db.execute(
        "SELECT p10_sales_org FROM market WHERE code=? AND active=1", (market,)
    ).fetchone()
    if market_row and market_row["p10_sales_org"] in user.get("admin_sales_org_access", []):
        return
    allowed = db.execute(
        "SELECT 1 FROM user_assignment ua "
        "JOIN market m ON m.code=ua.market_code "
        "JOIN user_sales_org so ON so.user_id=ua.user_id AND so.sales_org=m.p10_sales_org "
        "WHERE ua.user_id=? AND ua.market_code=? AND ua.customer_id=?",
        (user["id"], market, customer),
    ).fetchone()
    if not allowed:
        raise HTTPException(status_code=403, detail="Plan account is not assigned to your user")
