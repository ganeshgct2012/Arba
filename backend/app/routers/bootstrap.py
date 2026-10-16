"""Initial data the frontend loads after login."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser
from app.utils import future_weeks, historical_weeks

router = APIRouter(tags=['bootstrap'])


@router.get(f"{API_PREFIX}/bootstrap")
async def bootstrap(user: CurrentUser) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        if user["role"] == "ADMIN":
            market_query = (
                "SELECT code,name,plan_mode,p10_sales_org,horizon_weeks FROM market "
                "WHERE active=1 ORDER BY code"
            )
            customer_query = (
                "SELECT id,market_code,name FROM customer_l04 WHERE active=1 ORDER BY name"
            )
            listing_query = "SELECT market_code,customer_id,p09_code FROM listing"
            params: tuple[Any, ...] = ()
        else:
            admin_orgs = user.get("admin_sales_org_access", [])
            if admin_orgs:
                placeholders = ",".join("?" for _ in admin_orgs)
                market_query = (
                    "SELECT DISTINCT m.code,m.name,m.plan_mode,m.p10_sales_org,m.horizon_weeks "
                    "FROM market m LEFT JOIN user_sales_org so ON so.sales_org=m.p10_sales_org "
                    f"WHERE m.active=1 AND (m.p10_sales_org IN ({placeholders}) OR so.user_id=?) ORDER BY m.code"
                )
                customer_query = (
                    "SELECT DISTINCT c.id,c.market_code,c.name FROM customer_l04 c "
                    "JOIN market m ON m.code=c.market_code "
                    "LEFT JOIN user_assignment ua ON ua.market_code=c.market_code AND ua.customer_id=c.id "
                    f"WHERE c.active=1 AND (m.p10_sales_org IN ({placeholders}) OR ua.user_id=?) ORDER BY c.name"
                )
                listing_query = (
                    "SELECT l.market_code,l.customer_id,l.p09_code FROM listing l "
                    "JOIN market m ON m.code=l.market_code "
                    "LEFT JOIN user_assignment ua ON ua.market_code=l.market_code AND ua.customer_id=l.customer_id "
                    f"WHERE m.p10_sales_org IN ({placeholders}) OR ua.user_id=?"
                )
                params = (*admin_orgs, user["id"])
            else:
                market_query = (
                    "SELECT DISTINCT m.code,m.name,m.plan_mode,m.p10_sales_org,m.horizon_weeks "
                    "FROM market m JOIN user_sales_org so ON so.sales_org=m.p10_sales_org "
                    "WHERE m.active=1 AND so.user_id=? ORDER BY m.code"
                )
                customer_query = (
                    "SELECT DISTINCT c.id,c.market_code,c.name FROM customer_l04 c "
                    "JOIN user_assignment ua ON ua.market_code=c.market_code AND ua.customer_id=c.id "
                    "JOIN market m ON m.code=c.market_code "
                    "JOIN user_sales_org so ON so.user_id=ua.user_id AND so.sales_org=m.p10_sales_org "
                    "WHERE c.active=1 AND ua.user_id=? ORDER BY c.name"
                )
                listing_query = (
                    "SELECT DISTINCT l.market_code,l.customer_id,l.p09_code FROM listing l "
                    "JOIN user_assignment ua ON ua.market_code=l.market_code AND ua.customer_id=l.customer_id "
                    "WHERE ua.user_id=?"
                )
                params = (user["id"],)
        markets = [
            dict(r)
            for r in db.execute(market_query, params)
        ]
        customers = [
            dict(r)
            for r in db.execute(customer_query, params)
        ]
        products = [
            dict(r)
            for r in db.execute(
                "SELECT code,description,brand,sub_brand,category FROM product_p09 WHERE active=1 ORDER BY brand,description"
            )
        ]
        tactics = [
            dict(r)
            for r in db.execute("SELECT market_code,name FROM tactic WHERE active=1 ORDER BY name")
        ]
        listing_rows = [
            dict(r) for r in db.execute(listing_query, params)
        ]
    return {
        "user": user,
        "markets": markets,
        "customers": customers,
        "products": products,
        "tactics": tactics,
        "listings": listing_rows,
        "weeks": future_weeks(),
        "history_weeks": historical_weeks(),
    }
