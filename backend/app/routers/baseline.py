"""Weekly Volume screen: baseline grid, XLSX export/upload."""

from __future__ import annotations

import base64
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, check_assignment, require_role
from app.schemas import BaselineFileUpload, BaselineSave
from app.services.audit import audit
from app.services.master_data import master_file_rows, required_master_value
from app.services.planning import product_rows_for_account
from app.services.xlsx import build_xlsx
from app.utils import future_weeks, iso_week, utcnow, week_monday

router = APIRouter(tags=['baseline'])


@router.get(f"{API_PREFIX}/baseline")
async def get_baseline(market: str, customer_id: int, user: CurrentUser) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        market_row = db.execute(
            "SELECT plan_mode,horizon_weeks FROM market WHERE code=?", (market,)
        ).fetchone()
        if market_row is None:
            raise HTTPException(status_code=404, detail="Market not found")
        rows = product_rows_for_account(db, market, customer_id, include_approved=False)
        weeks = future_weeks(int(market_row["horizon_weeks"]))
        result = []
        for product in rows:
            baseline = {
                r["iso_week"]: r["qty_cs"]
                for r in db.execute(
                    "SELECT iso_week,qty_cs FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=?",
                    (market, customer_id, product["code"]),
                )
            }
            actual = {
                r["iso_week"]: r["qty_cs"]
                for r in db.execute(
                    "SELECT iso_week,qty_cs FROM actual_sellin WHERE market_code=? AND customer_id=? AND p09_code=?",
                    (market, customer_id, product["code"]),
                )
            }
            result.append(
                {
                    **dict(product),
                    "baseline": [baseline.get(w, 0) for w in weeks],
                    "actual_last_year": [
                        actual.get(iso_week(week_monday(w) - timedelta(weeks=52)), 0) for w in weeks
                    ],
                }
            )
    return {
        "market": market,
        "customer_id": customer_id,
        "plan_mode": market_row["plan_mode"],
        "weeks": weeks,
        "products": result,
    }


@router.put(f"{API_PREFIX}/baseline")
async def save_baseline(payload: BaselineSave, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "PLANNER")
    if not payload.cells:
        return {"saved": 0}
    with DB_LOCK, connect() as db:
        with db:
            market_row = db.execute(
                "SELECT plan_mode,horizon_weeks FROM market WHERE code=?",
                (payload.market,),
            ).fetchone()
            if market_row is None:
                raise HTTPException(status_code=404, detail="Market not found")
            check_assignment(db, user, payload.market, payload.customer_id)
            weeks = set(future_weeks(int(market_row["horizon_weeks"])))
            listed = {
                row["p09_code"]
                for row in db.execute(
                    "SELECT p09_code FROM listing WHERE market_code=? AND customer_id=?",
                    (payload.market, payload.customer_id),
                )
            }
            unique: set[tuple[str, str]] = set()
            values = []
            for cell in payload.cells:
                if not math.isfinite(cell.qty_cs):
                    raise HTTPException(
                        status_code=422, detail="Baseline values must be finite numbers"
                    )
                try:
                    week_monday(cell.week)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                if cell.week not in weeks:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Past or out-of-horizon week is locked: {cell.week}",
                    )
                if cell.product not in listed:
                    raise HTTPException(
                        status_code=400, detail=f"Product is not listed: {cell.product}"
                    )
                key = (cell.product, cell.week)
                if key in unique:
                    raise HTTPException(
                        status_code=422,
                        detail="Duplicate product/week cells in request",
                    )
                unique.add(key)
                values.append(
                    (
                        payload.market,
                        payload.customer_id,
                        cell.product,
                        cell.week,
                        cell.qty_cs,
                        "MANUAL",
                        user["email"],
                        utcnow().isoformat(),
                    )
                )
            db.executemany(
                "INSERT INTO baseline(market_code,customer_id,p09_code,iso_week,qty_cs,source,changed_by,changed_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(market_code,customer_id,p09_code,iso_week) "
                "DO UPDATE SET qty_cs=excluded.qty_cs,source=excluded.source,changed_by=excluded.changed_by,changed_at=excluded.changed_at",
                values,
            )
            audit(
                db,
                "baseline",
                f"{payload.market}:{payload.customer_id}",
                "BULK_UPSERT",
                user["email"],
                after={"cells": len(values)},
            )
    return {"saved": len(values)}


@router.get(f"{API_PREFIX}/baseline/export")
async def export_baseline(market: str, customer_id: int, user: CurrentUser) -> Response:
    with DB_LOCK, connect() as db:
        check_assignment(db, user, market, customer_id)
        market_row = db.execute(
            "SELECT plan_mode,horizon_weeks FROM market WHERE code=?", (market,)
        ).fetchone()
        if market_row is None:
            raise HTTPException(status_code=404, detail="Market not found")
        customer = db.execute(
            "SELECT id,external_code FROM customer_l04 WHERE market_code=? AND id=? AND active=1",
            (market, customer_id),
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Plan account not found")
        customer_code = customer["external_code"] or str(customer["id"])
        weeks = future_weeks(int(market_row["horizon_weeks"]))
        products = product_rows_for_account(db, market, customer_id, include_approved=False)
        rows = []
        for product in products:
            baseline_by_week = {
                row["iso_week"]: float(row["qty_cs"])
                for row in db.execute(
                    "SELECT iso_week,qty_cs FROM baseline WHERE market_code=? AND customer_id=? AND p09_code=?",
                    (market, customer_id, product["code"]),
                )
            }
            rows.extend(
                {
                    "Customer ID": str(customer_code),
                    "Product P09": product["code"],
                    "Week": week,
                    "Baseline Cases": str(baseline_by_week.get(week, 0)),
                }
                for week in weeks
            )
    columns = ("Customer ID", "Product P09", "Week", "Baseline Cases")
    filename = f"baseline_{market}_{customer_id}.xlsx"
    return Response(
        build_xlsx(rows, columns),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(f"{API_PREFIX}/baseline/upload")
async def upload_baseline(payload: BaselineFileUpload, user: CurrentUser) -> dict[str, int]:
    require_role(user, "PLANNER")
    if Path(payload.filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=415, detail="Upload a baseline XLSX workbook")
    try:
        contents = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="The upload is not valid base64 data") from exc
    if not contents or len(contents) > 10_000_000:
        raise HTTPException(status_code=413, detail="Baseline workbook must be between 1 byte and 10 MB")
    try:
        rows = master_file_rows(payload.filename, contents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not rows or len(rows) > 20_000:
        raise HTTPException(status_code=422, detail="Baseline workbook must contain between 1 and 20,000 data rows")

    with DB_LOCK, connect() as db:
        with db:
            market_row = db.execute(
                "SELECT plan_mode,horizon_weeks FROM market WHERE code=?", (payload.market,)
            ).fetchone()
            if market_row is None:
                raise HTTPException(status_code=404, detail="Market not found")
            check_assignment(db, user, payload.market, payload.customer_id)
            customer = db.execute(
                "SELECT id,external_code FROM customer_l04 WHERE market_code=? AND id=? AND active=1",
                (payload.market, payload.customer_id),
            ).fetchone()
            if customer is None:
                raise HTTPException(status_code=404, detail="Plan account not found")
            allowed_customer_ids = {str(customer["id"])}
            if customer["external_code"]:
                allowed_customer_ids.add(str(customer["external_code"]))
            weeks = set(future_weeks(int(market_row["horizon_weeks"])))
            listed = {
                row["p09_code"]
                for row in db.execute(
                    "SELECT p09_code FROM listing WHERE market_code=? AND customer_id=?",
                    (payload.market, payload.customer_id),
                )
            }
            unique: set[tuple[str, str]] = set()
            values = []
            for row_number, row in rows:
                customer_id_value = required_master_value(row, "Customer ID", "Customer L04")
                product = required_master_value(row, "Product P09", "P09", "Product")
                week = required_master_value(row, "Week", "ISO Week")
                quantity_text = required_master_value(row, "Baseline Cases", "Baseline")
                if customer_id_value not in allowed_customer_ids:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: Customer ID does not match the selected plan account",
                    )
                if product not in listed:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: P09 product is not listed for this plan account ({product})",
                    )
                try:
                    week_monday(week)
                    quantity = float(quantity_text)
                except (ValueError, OverflowError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: Week or Baseline Cases is invalid",
                    ) from exc
                if week not in weeks:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: Past or out-of-horizon week is locked ({week})",
                    )
                if not math.isfinite(quantity) or quantity < 0:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: Baseline Cases must be a non-negative number",
                    )
                key = (product, week)
                if key in unique:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {row_number}: Duplicate P09 product and week",
                    )
                unique.add(key)
                values.append(
                    (
                        payload.market,
                        payload.customer_id,
                        product,
                        week,
                        quantity,
                        "UPLOAD",
                        user["email"],
                        utcnow().isoformat(),
                    )
                )
            db.executemany(
                "INSERT INTO baseline(market_code,customer_id,p09_code,iso_week,qty_cs,source,changed_by,changed_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(market_code,customer_id,p09_code,iso_week) "
                "DO UPDATE SET qty_cs=excluded.qty_cs,source=excluded.source,"
                "changed_by=excluded.changed_by,changed_at=excluded.changed_at",
                values,
            )
            audit(
                db,
                "baseline",
                f"{payload.market}:{payload.customer_id}",
                "UPLOAD",
                user["email"],
                after={"cells": len(values), "filename": Path(payload.filename).name},
            )
    return {"saved": len(values)}
