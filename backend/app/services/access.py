"""Validation of user access assignments (sales orgs, plan accounts)."""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from app.schemas import UserAccessAssignment


def validate_user_access(
    db: sqlite3.Connection,
    sales_org_access: list[str],
    assignments: list[UserAccessAssignment],
) -> list[tuple[str, int]]:
    sales_orgs = set(sales_org_access)
    known_sales_orgs = {
        row["p10_sales_org"]
        for row in db.execute("SELECT p10_sales_org FROM market WHERE active=1")
    }
    if len(sales_orgs) != len(sales_org_access) or not sales_orgs <= known_sales_orgs:
        raise HTTPException(status_code=422, detail="Invalid or duplicate sales organization access")
    pairs = [(assignment.market_code, assignment.customer_id) for assignment in assignments]
    if len(pairs) != len(set(pairs)):
        raise HTTPException(status_code=422, detail="Duplicate plan-account assignments")
    for market_code, customer_id in pairs:
        assignment_row = db.execute(
            "SELECT m.p10_sales_org FROM customer_l04 c "
            "JOIN market m ON m.code=c.market_code "
            "WHERE c.market_code=? AND c.id=? AND c.active=1 AND m.active=1",
            (market_code, customer_id),
        ).fetchone()
        if assignment_row is None:
            raise HTTPException(
                status_code=422, detail=f"Invalid plan-account assignment: {market_code}/{customer_id}"
            )
        if assignment_row["p10_sales_org"] not in sales_orgs:
            raise HTTPException(
                status_code=422,
                detail=f"Sales organization access is required for plan account {market_code}/{customer_id}",
            )
    return pairs


def validate_admin_sales_org_access(
    admin_sales_org_access: list[str], sales_org_access: list[str]
) -> list[str]:
    admin_orgs = set(admin_sales_org_access)
    if len(admin_orgs) != len(admin_sales_org_access):
        raise HTTPException(status_code=422, detail="Duplicate administrator sales organization access")
    if not admin_orgs.issubset(set(sales_org_access)):
        raise HTTPException(
            status_code=422,
            detail="Administrator access must be included in the user's sales organization access",
        )
    return sorted(admin_orgs)
