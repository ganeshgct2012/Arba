"""Demo data loaded on first run (markets, accounts, products, users, baselines)."""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import date, timedelta

from app.config import ACCOUNTS, MARKETS, PIPELINES, PRODUCTS, TACTICS
from app.security import password_hash
from app.services.audit import log_status
from app.utils import future_weeks, historical_weeks, utcnow


def seed_database(db: sqlite3.Connection) -> None:
    db.executemany(
        "INSERT INTO market(code,name,plan_mode,p10_sales_org,horizon_weeks) VALUES(?,?,?,?,52)",
        MARKETS,
    )
    accounts: dict[tuple[str, str], int] = {}
    for market_code, _, _, _ in MARKETS:
        for account_code, account_name in ACCOUNTS:
            cursor = db.execute(
                "INSERT INTO customer_l04(market_code,name,parent_l03) VALUES(?,?,?)",
                (market_code, account_name, f"{market_code}-L03-01"),
            )
            accounts[(market_code, account_code)] = int(cursor.lastrowid)

    brands = sorted({product[2] for product in PRODUCTS})
    for brand in brands:
        parent: str | None = None
        for level in range(1, 9):
            node_id = f"P{level}-{brand.upper().replace(' ', '-')}"
            db.execute(
                "INSERT INTO product_hierarchy(node_id,parent_id,level,code,text) VALUES(?,?,?,?,?)",
                (
                    node_id,
                    parent,
                    level,
                    f"{brand[:3].upper()}-{level}",
                    f"{brand} level {level}",
                ),
            )
            parent = node_id
        brand_parent[brand] = parent

    for code, description, brand, sub_brand, category, material_count in PRODUCTS:
        db.execute(
            "INSERT INTO product_hierarchy(node_id,parent_id,level,code,text) VALUES(?,?,9,?,?)",
            (code, brand_parent[brand], code, description),
        )
        db.execute(
            "INSERT INTO product_p09(code,description,brand,sub_brand,category,hierarchy_node_id) "
            "VALUES(?,?,?,?,?,?)",
            (code, description, brand, sub_brand, category, code),
        )
        for index in range(material_count):
            material = f"MAT-{code[-4:]}-{index + 1:02d}"
            share = 100 / material_count
            db.execute(
                "INSERT INTO material_p10(material,description,p09_code,case_uom) VALUES(?,?,?,'CS')",
                (material, f"{description} order material {index + 1}", code),
            )
            db.execute(
                "INSERT INTO p09_p10_split(p09_code,material,share,valid_from,source) "
                "VALUES(?,?,?,?, 'CALC')",
                (code, material, share, date.today().isoformat()),
            )

    for market, _, _, _ in MARKETS:
        db.executemany(
            "INSERT INTO tactic(market_code,name) VALUES(?,?)",
            [(market, tactic) for tactic in TACTICS],
        )

    initial_password = os.getenv("ARBA_INITIAL_PASSWORD")
    if not initial_password:
        initial_password = secrets.token_urlsafe(15)
        print(
            f"\nArBa first-run password (admin@arba.local): {initial_password}\n",
            flush=True,
        )
        print(
            "Use this password for the seeded demo users; set ARBA_INITIAL_PASSWORD to choose one.",
            flush=True,
        )
    if len(initial_password) < 12:
        raise ValueError("ARBA_INITIAL_PASSWORD must contain at least 12 characters")
    users = (
        ("admin@arba.local", "ArBa Administrator", "ADMIN"),
        ("planner@arba.local", "Demo Planner", "PLANNER"),
        ("approver@arba.local", "Demo Approver", "APPROVER"),
        ("viewer@arba.local", "Demo Viewer", "VIEWER"),
    )
    user_ids: dict[str, int] = {}
    for email, name, role in users:
        cursor = db.execute(
            "INSERT INTO app_user(email,name,role,password_hash,is_seed) VALUES(?,?,?,?,1)",
            (email, name, role, password_hash(initial_password)),
        )
        user_ids[role] = int(cursor.lastrowid)
    for role in ("PLANNER", "APPROVER", "VIEWER"):
        db.executemany(
            "INSERT INTO user_sales_org(user_id,sales_org) VALUES(?,?)",
            [(user_ids[role], sales_org) for _, _, _, sales_org in MARKETS],
        )
    for (market_code, _), customer_id in accounts.items():
        for role in ("PLANNER", "APPROVER", "VIEWER"):
            db.execute(
                "INSERT INTO user_assignment(user_id,market_code,customer_id) VALUES(?,?,?)",
                (user_ids[role], market_code, customer_id),
            )

    weeks_back, weeks_ahead = historical_weeks(), future_weeks()
    listed = [p[0] for p in PRODUCTS]
    now_text = utcnow().isoformat()
    for (market_code, _), customer_id in accounts.items():
        db.executemany(
            "INSERT INTO listing(market_code,customer_id,p09_code,created_by,created_at) "
            "VALUES(?,?,?,'seed',?)",
            [(market_code, customer_id, product, now_text) for product in listed],
        )
        actual_rows = []
        for p_index, product in enumerate(listed):
            for w_index, week in enumerate(weeks_back):
                actual_rows.append(
                    (
                        market_code,
                        customer_id,
                        product,
                        week,
                        20 + p_index * 3 + w_index % 11,
                        now_text,
                    )
                )
        db.executemany(
            "INSERT INTO actual_sellin(market_code,customer_id,p09_code,iso_week,qty_cs,loaded_at) "
            "VALUES(?,?,?,?,?,?)",
            actual_rows,
        )
        baseline_rows = []
        for p_index, product in enumerate(listed):
            for w_index, week in enumerate(weeks_ahead):
                baseline_rows.append(
                    (
                        market_code,
                        customer_id,
                        product,
                        week,
                        40 + p_index * 4 + w_index % 9,
                        "MANUAL",
                        "seed",
                        now_text,
                    )
                )
        db.executemany(
            "INSERT INTO baseline(market_code,customer_id,p09_code,iso_week,qty_cs,source,changed_by,changed_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            baseline_rows,
        )

    promo_markets = [m[0] for m in MARKETS if m[2] == "PROMO"]
    current_monday = date.today() - timedelta(days=date.today().weekday())
    for index, promo_status in enumerate(("NEW", "SAVED", "CHANGED", "APPROVED")):
        market = promo_markets[index]
        customer = accounts[(market, ACCOUNTS[index][0])]
        start = current_monday + timedelta(weeks=index + 4)
        end = start + timedelta(days=6)
        promo_number = f"PR{index + 1:06d}"
        cursor = db.execute(
            "INSERT INTO promotion(promo_number,market_code,customer_id,start_date,end_date,cons_start,cons_end,"
            "tactic,status,created_by,created_at,approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                promo_number,
                market,
                customer,
                start.isoformat(),
                end.isoformat(),
                start.isoformat(),
                end.isoformat(),
                TACTICS[index],
                promo_status,
                "planner@arba.local",
                now_text,
                "approver@arba.local" if promo_status == "APPROVED" else None,
                now_text if promo_status == "APPROVED" else None,
            ),
        )
        promo_id = int(cursor.lastrowid)
        log_status(db, promo_id, "planner@arba.local", None, "NEW")
        db.execute(
            "INSERT INTO promotion_item(promotion_id,p09_code,total_cs) VALUES(?,?,?)",
            (promo_id, PRODUCTS[index][0], 200 + index * 25),
        )
        db.execute(
            "INSERT INTO promotion_status_log(promotion_id,ts,user,old_status,new_status) VALUES(?,?,?,?,?)",
            (promo_id, now_text, "planner@arba.local", None, promo_status),
        )

    db.executemany(
        "INSERT INTO pipeline(id,name,direction,source,target,connector_type,schedule_cron,enabled) "
        "VALUES(?,?,?,?,?,?,?,1)",
        [
            (pid, name, direction, source, target, connector, "0 2 * * *")
            for pid, name, direction, source, target, connector in PIPELINES
        ],
    )
    db.commit()


# This name is filled during first-run seed creation.
brand_parent: dict[str, str | None] = {}
