"""Configuration > Access Management (users) and audit log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, require_access_administrator, require_role
from app.schemas import AdminUserCreate, AdminUserUpdate
from app.security import password_hash
from app.services.access import validate_admin_sales_org_access, validate_user_access
from app.services.audit import audit
from app.utils import utcnow

router = APIRouter(tags=['admin_users'])


@router.post(f"{API_PREFIX}/admin/users", status_code=201)
async def create_admin_user(payload: AdminUserCreate, user: CurrentUser) -> dict[str, Any]:
    require_access_administrator(user)
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="User name must contain at least 2 characters")
    with DB_LOCK, connect() as db:
        with db:
            pairs = validate_user_access(db, payload.sales_org_access, payload.assignments)
            requested_admin_orgs = validate_admin_sales_org_access(
                payload.admin_sales_org_access, payload.sales_org_access
            )
            if db.execute(
                "SELECT 1 FROM app_user WHERE email=? COLLATE NOCASE", (email,)
            ).fetchone():
                raise HTTPException(status_code=409, detail="A user with this email already exists")
            cursor = db.execute(
                "INSERT INTO app_user(email,name,role,password_hash,active,last_login_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    email,
                    name,
                    payload.role,
                    password_hash(payload.password),
                    int(payload.active),
                    utcnow().isoformat(),
                ),
            )
            user_id = int(cursor.lastrowid)
            db.executemany(
                "INSERT INTO user_sales_org(user_id,sales_org) VALUES(?,?)",
                [(user_id, sales_org) for sales_org in sorted(set(payload.sales_org_access))],
            )
            first_admin_orgs = [
                sales_org
                for sales_org in sorted(set(payload.sales_org_access))
                if not db.execute(
                    "SELECT 1 FROM user_sales_org so JOIN app_user u ON u.id=so.user_id "
                    "WHERE so.sales_org=? AND so.user_id<>? AND u.is_seed=0 LIMIT 1",
                    (sales_org, user_id),
                ).fetchone()
            ]
            effective_admin_orgs = sorted(set(requested_admin_orgs) | set(first_admin_orgs))
            db.executemany(
                "INSERT INTO user_sales_org_admin(user_id,sales_org) VALUES(?,?)",
                [(user_id, sales_org) for sales_org in effective_admin_orgs],
            )
            db.executemany(
                "INSERT INTO user_assignment(user_id,market_code,customer_id) VALUES(?,?,?)",
                [(user_id, market_code, customer_id) for market_code, customer_id in pairs],
            )
            audit(
                db,
                "app_user",
                str(user_id),
                "CREATE",
                user["email"],
                after={
                    "email": email,
                    "name": name,
                    "role": payload.role,
                    "sales_org_access": payload.sales_org_access,
                    "assignments": pairs,
                    "admin_sales_org_access": effective_admin_orgs,
                },
            )
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "role": payload.role,
        "sales_org_access": sorted(set(payload.sales_org_access)),
        "admin_sales_org_access": effective_admin_orgs,
        "first_admin_sales_orgs": first_admin_orgs,
        "assignments": len(pairs),
    }


@router.get(f"{API_PREFIX}/admin/users")
async def admin_users(user: CurrentUser) -> dict[str, Any]:
    require_access_administrator(user)
    with DB_LOCK, connect() as db:
        users = []
        user_query = "SELECT id,email,name,role,active,last_login_at FROM app_user"
        if user["role"] != "ADMIN":
            user_query += " WHERE role<>'ADMIN'"
        user_query += " ORDER BY email"
        for row in db.execute(user_query):
            result = dict(row)
            result["sales_org_access"] = [
                item["sales_org"]
                for item in db.execute(
                    "SELECT sales_org FROM user_sales_org WHERE user_id=? ORDER BY sales_org",
                    (row["id"],),
                )
            ]
            result["admin_sales_org_access"] = [
                item["sales_org"]
                for item in db.execute(
                    "SELECT sales_org FROM user_sales_org_admin WHERE user_id=? ORDER BY sales_org",
                    (row["id"],),
                )
            ]
            users.append(result)
        assignments = [
            dict(r)
            for r in db.execute(
                "SELECT ua.user_id,u.email,ua.market_code,ua.customer_id,c.name AS customer_name "
                "FROM user_assignment ua JOIN app_user u ON u.id=ua.user_id "
                "JOIN customer_l04 c ON c.id=ua.customer_id ORDER BY u.email,ua.market_code,c.name"
            )
        ]
        sales_orgs = [
            dict(row)
            for row in db.execute(
                "SELECT p10_sales_org AS code,name FROM market WHERE active=1 ORDER BY p10_sales_org"
            )
        ]
    return {"users": users, "assignments": assignments, "sales_orgs": sales_orgs}


@router.put(f"{API_PREFIX}/admin/users/{{user_id}}")
async def update_admin_user(
    user_id: int, payload: AdminUserUpdate, user: CurrentUser
) -> dict[str, Any]:
    require_access_administrator(user)
    with DB_LOCK, connect() as db:
        with db:
            pairs = validate_user_access(db, payload.sales_org_access, payload.assignments)
            admin_orgs = validate_admin_sales_org_access(
                payload.admin_sales_org_access, payload.sales_org_access
            )
            target = db.execute(
                "SELECT id,email,name,role,active FROM app_user WHERE id=?", (user_id,)
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="User not found")
            current_sales_orgs = {
                row["sales_org"]
                for row in db.execute(
                    "SELECT sales_org FROM user_sales_org WHERE user_id=?",
                    (user_id,),
                )
            }
            if user["role"] != "ADMIN" and target["role"] == "ADMIN":
                raise HTTPException(
                    status_code=403,
                    detail="Only a system administrator can change a system administrator account",
                )
            if user["role"] != "ADMIN" and payload.role == "ADMIN":
                raise HTTPException(
                    status_code=403,
                    detail="Use administrator sales organization access instead of the global system administrator role",
                )
            if user["role"] != "ADMIN":
                current_admin_orgs = {
                    row["sales_org"]
                    for row in db.execute(
                        "SELECT sales_org FROM user_sales_org_admin WHERE user_id=?",
                        (user_id,),
                    )
                }
                removed_admin_orgs = current_admin_orgs - set(admin_orgs)
                if not payload.active:
                    removed_admin_orgs.update(current_admin_orgs)
                for sales_org in removed_admin_orgs:
                    replacement = db.execute(
                        "SELECT 1 FROM app_user u "
                        "LEFT JOIN user_sales_org_admin usa ON usa.user_id=u.id "
                        "WHERE u.active=1 AND u.id<>? AND "
                        "(u.role='ADMIN' OR usa.sales_org=?) LIMIT 1",
                        (user_id, sales_org),
                    ).fetchone()
                    if replacement is None:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Assign another active administrator to {sales_org} before removing the last one",
                        )
            first_admin_orgs = [
                sales_org
                for sales_org in sorted(set(payload.sales_org_access) - current_sales_orgs)
                if not db.execute(
                    "SELECT 1 FROM user_sales_org so JOIN app_user u ON u.id=so.user_id "
                    "WHERE so.sales_org=? AND so.user_id<>? AND u.is_seed=0 LIMIT 1",
                    (sales_org, user_id),
                ).fetchone()
            ]
            effective_admin_orgs = sorted(set(admin_orgs) | set(first_admin_orgs))
            for market_code, customer_id in pairs:
                assignment_exists = db.execute(
                    "SELECT 1 FROM customer_l04 WHERE market_code=? AND id=? AND active=1",
                    (market_code, customer_id),
                ).fetchone()
                if assignment_exists is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid plan-account assignment: {market_code}/{customer_id}",
                    )
            before = {
                "role": target["role"],
                "active": bool(target["active"]),
                "assignments": [
                    {"market_code": row["market_code"], "customer_id": row["customer_id"]}
                    for row in db.execute(
                        "SELECT market_code,customer_id FROM user_assignment WHERE user_id=?",
                        (user_id,),
                    )
                ],
                "sales_org_access": [
                    row["sales_org"]
                    for row in db.execute(
                        "SELECT sales_org FROM user_sales_org WHERE user_id=?",
                        (user_id,),
                    )
                ],
                "admin_sales_org_access": [
                    row["sales_org"]
                    for row in db.execute(
                        "SELECT sales_org FROM user_sales_org_admin WHERE user_id=?",
                        (user_id,),
                    )
                ],
            }
            db.execute(
                "UPDATE app_user SET role=?,active=? WHERE id=?",
                (payload.role, int(payload.active), user_id),
            )
            db.execute("DELETE FROM user_assignment WHERE user_id=?", (user_id,))
            db.executemany(
                "INSERT INTO user_assignment(user_id,market_code,customer_id) VALUES(?,?,?)",
                [(user_id, market_code, customer_id) for market_code, customer_id in pairs],
            )
            db.execute("DELETE FROM user_sales_org WHERE user_id=?", (user_id,))
            db.executemany(
                "INSERT INTO user_sales_org(user_id,sales_org) VALUES(?,?)",
                [(user_id, sales_org) for sales_org in sorted(set(payload.sales_org_access))],
            )
            db.execute("DELETE FROM user_sales_org_admin WHERE user_id=?", (user_id,))
            db.executemany(
                "INSERT INTO user_sales_org_admin(user_id,sales_org) VALUES(?,?)",
                [(user_id, sales_org) for sales_org in effective_admin_orgs],
            )
            audit(
                db,
                "app_user",
                str(user_id),
                "UPDATE_ACCESS",
                user["email"],
                before=before,
                after={
                    **payload.model_dump(),
                    "admin_sales_org_access": effective_admin_orgs,
                },
            )
    return {
        "id": user_id,
        "role": payload.role,
        "active": payload.active,
        "assignments": len(pairs),
        "admin_sales_org_access": effective_admin_orgs,
        "first_admin_sales_orgs": first_admin_orgs,
    }


@router.get(f"{API_PREFIX}/admin/audit")
async def admin_audit(user: CurrentUser, limit: int = 100) -> dict[str, Any]:
    require_role(user, "ADMIN")
    limit = max(1, min(limit, 500))
    with DB_LOCK, connect() as db:
        rows = [
            dict(r)
            for r in db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
        ]
    return {"events": rows}
