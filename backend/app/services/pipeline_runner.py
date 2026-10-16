"""Executes an integration pipeline (manual or scheduled run)."""

from __future__ import annotations

import csv
import io
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

from app.config import INBOUND_PROCESSED_DIR, logger
from app.db import DB_LOCK, connect
from app.deps import require_role
from app.services.audit import audit
from app.services.files import store_outbound_file, validate_pipeline_file_location
from app.services.master_data import master_file_rows
from app.services.p10_feed import P10_COLUMNS, build_p10_rows
from app.services.xlsx import build_xlsx
from app.utils import utcnow


async def execute_pipeline(
    pipeline_id: str,
    user: dict[str, Any],
    dry_run: bool = True,
    trigger: Literal["MANUAL", "SCHEDULE"] = "MANUAL",
) -> dict[str, Any]:
    require_role(user, "ADMIN")
    started = utcnow().isoformat()
    outbound_rows: list[dict[str, str]] = []
    outbound_market = ""
    custom_outbound: list[tuple[str, dict[str, str]]] = []
    custom_inbound_archive: tuple[Path, str, int] | None = None
    with DB_LOCK, connect() as db:
        with db:
            pipeline = db.execute("SELECT * FROM pipeline WHERE id=?", (pipeline_id,)).fetchone()
            if not pipeline:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            cursor = db.execute(
                "INSERT INTO pipeline_run(pipeline_id,trigger,status,started_at,message) VALUES(?,?,'RUNNING',?,?)",
                (
                    pipeline_id,
                    trigger,
                    started,
                    "Dry run" if dry_run else "Mock connector execution",
                ),
            )
            run_id = int(cursor.lastrowid)
            count = db.execute("SELECT COUNT(*) AS n FROM market WHERE active=1").fetchone()["n"]
            status_value = "SUCCESS"
            message = f"Mock {pipeline['connector_type']} completed; dry_run={str(dry_run).lower()}"
            if pipeline_id == "OUT-01":
                try:
                    outbound_market = db.execute(
                        "SELECT code FROM market WHERE active=1 ORDER BY code LIMIT 1"
                    ).fetchone()["code"]
                    rows = build_p10_rows(
                        db,
                        outbound_market,
                    )
                    outbound_rows = rows
                    if not dry_run:
                        db.executemany(
                            "INSERT INTO p10_outbound(run_id,market_code,start_date,end_date,plan_account,material,base,lift,total,promo_number,cons_start,cons_end,sales_org) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            [
                                (
                                    run_id,
                                    outbound_market,
                                    r["Start Date"][:10],
                                    r["End Date"][:10],
                                    r["Plan Account"],
                                    r["Material Number"],
                                    int(r["BaseVolume"]),
                                    int(r["LiftVolume"]),
                                    int(r["TotalVolume"]),
                                    r["PromoNumber"],
                                    r["Consumption Start"][:10],
                                    r["Consumption End"][:10],
                                    r["Sales Org"],
                                )
                                for r in rows
                            ],
                        )
                    count = len(rows)
                except HTTPException as exc:
                    status_value = "FAILED"
                    message = str(exc.detail)
                    count = 0
            elif pipeline["connector_type"] == "FileConnector":
                config = json.loads(pipeline["config_json"])
                path_error = None
                try:
                    configured_path = validate_pipeline_file_location(
                        config.get("file_path"), pipeline["direction"]
                    )
                except HTTPException as exc:
                    configured_path = None
                    path_error = str(exc.detail)
                if configured_path is None:
                    status_value = "FAILED"
                    message = path_error or "FileConnector has no configured file location"
                    count = 0
                elif configured_path.suffix.lower() not in {".csv", ".xlsx"}:
                    status_value = "FAILED"
                    message = "FileConnector files must use .csv or .xlsx"
                    count = 0
                elif pipeline["direction"] == "INBOUND":
                    try:
                        if not configured_path.is_file():
                            raise FileNotFoundError(f"Configured inbound file does not exist: {configured_path}")
                        parsed_rows = master_file_rows(
                            configured_path.name, configured_path.read_bytes()
                        )
                        count = len(parsed_rows)
                        if not dry_run:
                            archived_path = INBOUND_PROCESSED_DIR / (
                                f"{secrets.token_hex(8)}_{Path(configured_path.name).name}"
                            )
                            configured_path.replace(archived_path)
                            custom_inbound_archive = (
                                archived_path,
                                configured_path.name,
                                count,
                            )
                            status_value = "PARTIAL"
                            message = (
                                f"Validated and archived {count} rows. A target-specific "
                                "master-data mapping is required to load these rows into ArBa."
                            )
                        else:
                            message = f"Validated {count} rows from {configured_path.name}; no data was changed."
                    except (OSError, ValueError) as exc:
                        status_value = "FAILED"
                        message = str(exc)
                        count = 0
                elif pipeline["direction"] == "OUTBOUND":
                    try:
                        for market_row in db.execute(
                            "SELECT code,p10_sales_org FROM market WHERE active=1 ORDER BY code"
                        ):
                            rows = build_p10_rows(db, market_row["code"])
                            custom_outbound.extend(
                                (market_row["code"], row) for row in rows
                            )
                        count = len(custom_outbound)
                        if not dry_run:
                            if configured_path.suffix.lower() == ".xlsx":
                                content = build_xlsx([row for _, row in custom_outbound])
                            elif configured_path.suffix.lower() == ".csv":
                                output = io.StringIO(newline="")
                                writer = csv.DictWriter(output, fieldnames=P10_COLUMNS)
                                writer.writeheader()
                                writer.writerows(row for _, row in custom_outbound)
                                content = output.getvalue().encode("utf-8-sig")
                            else:
                                raise ValueError("Outbound FileConnector location must end in .csv or .xlsx")
                            configured_path.parent.mkdir(parents=True, exist_ok=True)
                            configured_path.write_bytes(content)
                            db.executemany(
                                "INSERT INTO p10_outbound(run_id,market_code,start_date,end_date,plan_account,material,base,lift,total,promo_number,cons_start,cons_end,sales_org) "
                                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                [
                                    (
                                        run_id,
                                        market_code,
                                        row["Start Date"][:10],
                                        row["End Date"][:10],
                                        row["Plan Account"],
                                        row["Material Number"],
                                        int(row["BaseVolume"]),
                                        int(row["LiftVolume"]),
                                        int(row["TotalVolume"]),
                                        row["PromoNumber"],
                                        row["Consumption Start"][:10],
                                        row["Consumption End"][:10],
                                        row["Sales Org"],
                                    )
                                    for market_code, row in custom_outbound
                                ],
                            )
                            db.execute(
                                "INSERT INTO managed_file(direction,category,original_name,stored_path,status,uploaded_by,created_at,processed_at,row_count,message) "
                                "VALUES('OUTBOUND',?,?,?,'PROCESSED',?,?,?,?,?)",
                                (
                                    pipeline_id,
                                    configured_path.name,
                                    str(configured_path),
                                    user["email"],
                                    utcnow().isoformat(),
                                    utcnow().isoformat(),
                                    count,
                                    f"Generated by pipeline {pipeline_id}",
                                ),
                            )
                            message = f"Wrote {count} P10 rows to {configured_path}"
                        else:
                            message = f"Prepared {count} P10 rows; no file was written."
                    except (OSError, ValueError, HTTPException) as exc:
                        status_value = "FAILED"
                        message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                        count = 0
            db.execute(
                "UPDATE pipeline_run SET status=?,finished_at=?,rows_read=?,rows_written=?,rows_rejected=0,message=? WHERE id=?",
                (
                    status_value,
                    utcnow().isoformat(),
                    count,
                    0 if dry_run else count,
                    message,
                    run_id,
                ),
            )
            audit(
                db,
                "pipeline_run",
                str(run_id),
                trigger,
                user["email"],
                after={
                    "pipeline": pipeline_id,
                    "dry_run": dry_run,
                    "status": status_value,
                },
            )
            if custom_inbound_archive is not None:
                archive, original_name, rows_written = custom_inbound_archive
                db.execute(
                    "INSERT INTO managed_file(direction,category,original_name,stored_path,status,uploaded_by,created_at,processed_at,row_count,message) "
                    "VALUES('INBOUND',?,?,?,'PROCESSED',?,?,?,?,?)",
                    (
                        pipeline_id,
                        original_name,
                        str(archive),
                        user["email"],
                        started,
                        utcnow().isoformat(),
                        rows_written,
                        "Validated and archived; no target-specific master-data mapping is configured.",
                    ),
                )
    if pipeline_id == "OUT-01" and not dry_run and status_value == "SUCCESS":
        try:
            store_outbound_file(
                f"arba_p10_{outbound_market}_run_{run_id}.xlsx",
                "OUT-01",
                build_xlsx(outbound_rows),
                user["email"],
            )
        except (OSError, sqlite3.Error):
            logger.exception("Unable to store outbound file for pipeline run %s", run_id)
            status_value = "FAILED"
            message = "P10 payload was generated but could not be stored in Outbound Files"
            with DB_LOCK, connect() as db:
                db.execute(
                    "UPDATE pipeline_run SET status='FAILED',finished_at=?,message=? WHERE id=?",
                    (utcnow().isoformat(), message, run_id),
                )
    return {"run_id": run_id, "status": status_value, "message": message}
