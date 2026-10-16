"""Configuration > Batch Job Configuration (pipelines)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException

from app.config import API_PREFIX
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, require_role
from app.schemas import PipelineCreate, PipelineUpdate
from app.services.audit import audit
from app.services.files import validate_pipeline_file_location
from app.services.pipeline_runner import execute_pipeline
from app.services.scheduler import next_pipeline_run

router = APIRouter(tags=['pipelines'])


@router.get(f"{API_PREFIX}/admin/pipelines")
async def pipelines(user: CurrentUser) -> dict[str, Any]:
    require_role(user, "ADMIN")
    with DB_LOCK, connect() as db:
        result = []
        for pipeline in db.execute("SELECT * FROM pipeline ORDER BY id"):
            last = db.execute(
                "SELECT * FROM pipeline_run WHERE pipeline_id=? ORDER BY id DESC LIMIT 1",
                (pipeline["id"],),
            ).fetchone()
            result.append(
                {
                    **dict(pipeline),
                    "config_json": json.loads(pipeline["config_json"]),
                    "last_run": dict(last) if last else None,
                    "next_run_at": next_pipeline_run(pipeline),
                }
            )
    return {"pipelines": result}


@router.put(f"{API_PREFIX}/admin/pipelines/{{pipeline_id}}")
async def update_pipeline(
    pipeline_id: str, payload: PipelineUpdate, user: CurrentUser
) -> dict[str, Any]:
    require_role(user, "ADMIN")
    try:
        ZoneInfo(payload.schedule_timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown schedule timezone") from exc
    if payload.schedule_start_date and payload.schedule_end_date and payload.schedule_end_date < payload.schedule_start_date:
        raise HTTPException(status_code=422, detail="Schedule end date must be on or after its start date")
    with DB_LOCK, connect() as db:
        with db:
            current = db.execute(
                "SELECT config_json,direction,connector_type FROM pipeline WHERE id=?", (pipeline_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            config = json.loads(current["config_json"])
            file_path = payload.file_path if payload.file_path is not None else config.get("file_path")
            resolved_path = validate_pipeline_file_location(file_path, current["direction"])
            if current["connector_type"] == "FileConnector" and resolved_path is None:
                raise HTTPException(status_code=422, detail="FileConnector requires an ArBa file location")
            if current["connector_type"] == "FileConnector" and resolved_path:
                if resolved_path.suffix.lower() not in {".csv", ".xlsx"}:
                    raise HTTPException(status_code=422, detail="FileConnector files must use .csv or .xlsx")
            if payload.file_path is not None:
                config["file_path"] = payload.file_path.strip() or None
            cursor = db.execute(
                "UPDATE pipeline SET enabled=?,schedule_frequency=?,schedule_timezone=?,schedule_time=?,"
                "schedule_weekday=?,schedule_month_day=?,schedule_quarter_month=?,schedule_start_date=?,"
                "schedule_end_date=?,last_schedule_key=NULL,config_json=?,"
                "schedule_cron=? WHERE id=?",
                (
                    int(payload.enabled),
                    payload.schedule_frequency,
                    payload.schedule_timezone,
                    payload.schedule_time,
                    payload.schedule_weekday,
                    payload.schedule_month_day,
                    payload.schedule_quarter_month,
                    payload.schedule_start_date.isoformat() if payload.schedule_start_date else None,
                    payload.schedule_end_date.isoformat() if payload.schedule_end_date else None,
                    json.dumps(config),
                    f"{payload.schedule_time} {payload.schedule_frequency}",
                    pipeline_id,
                ),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Pipeline not found")
            audit(
                db,
                "pipeline",
                pipeline_id,
                "UPDATE",
                user["email"],
                after=payload.model_dump(),
            )
    return {"id": pipeline_id, **payload.model_dump()}


@router.post(f"{API_PREFIX}/admin/pipelines", status_code=201)
async def create_pipeline(payload: PipelineCreate, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "ADMIN")
    try:
        ZoneInfo(payload.schedule_timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown schedule timezone") from exc
    if payload.schedule_start_date and payload.schedule_end_date and payload.schedule_end_date < payload.schedule_start_date:
        raise HTTPException(status_code=422, detail="Schedule end date must be on or after its start date")
    validate_pipeline_file_location(payload.file_path, payload.direction)
    if payload.connector_type == "FileConnector" and not payload.file_path:
        raise HTTPException(status_code=422, detail="FileConnector requires an ArBa file location")
    if payload.connector_type == "FileConnector" and Path(payload.file_path).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=422, detail="FileConnector files must use .csv or .xlsx")
    pipeline_id = f"CUSTOM-{secrets.token_hex(4).upper()}"
    config = {"file_path": payload.file_path.strip() if payload.file_path else None}
    with DB_LOCK, connect() as db:
        with db:
            db.execute(
                "INSERT INTO pipeline(id,name,direction,source,target,connector_type,schedule_cron,enabled,"
                "config_json,schedule_frequency,schedule_timezone,schedule_time,schedule_weekday,"
                "schedule_month_day,schedule_quarter_month,schedule_start_date,schedule_end_date) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    pipeline_id,
                    payload.name.strip(),
                    payload.direction,
                    payload.source.strip(),
                    payload.target.strip(),
                    payload.connector_type,
                    f"{payload.schedule_time} {payload.schedule_frequency}",
                    int(payload.enabled),
                    json.dumps(config),
                    payload.schedule_frequency,
                    payload.schedule_timezone,
                    payload.schedule_time,
                    payload.schedule_weekday,
                    payload.schedule_month_day,
                    payload.schedule_quarter_month,
                    payload.schedule_start_date.isoformat() if payload.schedule_start_date else None,
                    payload.schedule_end_date.isoformat() if payload.schedule_end_date else None,
                ),
            )
            audit(
                db,
                "pipeline",
                pipeline_id,
                "CREATE",
                user["email"],
                after={**payload.model_dump(), "config_json": config},
            )
    return {"id": pipeline_id, **payload.model_dump(), "config_json": config}


@router.post(f"{API_PREFIX}/admin/pipelines/{{pipeline_id}}/run")
async def run_pipeline(
    pipeline_id: str,
    user: CurrentUser,
    dry_run: bool = True,
    trigger: Literal["MANUAL", "SCHEDULE"] = "MANUAL",
) -> dict[str, Any]:
    return await execute_pipeline(pipeline_id, user, dry_run=dry_run, trigger=trigger)


@router.get(f"{API_PREFIX}/admin/pipelines/{{pipeline_id}}/runs")
async def pipeline_runs(pipeline_id: str, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "ADMIN")
    with DB_LOCK, connect() as db:
        if not db.execute("SELECT 1 FROM pipeline WHERE id=?", (pipeline_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Pipeline not found")
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM pipeline_run WHERE pipeline_id=? ORDER BY id DESC LIMIT 100",
                (pipeline_id,),
            )
        ]
    return {"runs": rows}
