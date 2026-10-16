"""Configuration > master data upload and managed files."""

from __future__ import annotations

import base64
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response

from app.config import (
    API_PREFIX,
    INBOUND_PROCESSED_DIR,
    INBOUND_QUEUE_DIR,
    OUTBOUND_DIR,
)
from app.db import DB_LOCK, connect
from app.deps import CurrentUser, require_role
from app.schemas import MasterFileUpload
from app.services.audit import audit
from app.services.master_data import master_file_rows, process_master_file
from app.utils import utcnow

router = APIRouter(tags=['files'])


@router.post(f"{API_PREFIX}/admin/master-data/{{master_type}}/upload", status_code=201)
async def upload_master_file(
    master_type: Literal["customer", "product"],
    payload: MasterFileUpload,
    user: CurrentUser,
) -> dict[str, Any]:
    require_role(user, "ADMIN")
    name = Path(payload.filename.replace("\\", "/")).name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,199}", name):
        raise HTTPException(status_code=422, detail="A valid source filename is required")
    try:
        contents = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="The upload is not valid base64 data") from exc
    if not contents or len(contents) > 10_000_000:
        raise HTTPException(status_code=413, detail="Master extract must be between 1 byte and 10 MB")
    if Path(name).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Upload a CSV or XLSX master extract")
    try:
        master_file_rows(name, contents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    file_id = secrets.token_hex(16)
    destination = INBOUND_QUEUE_DIR / f"{file_id}{Path(name).suffix.lower()}"
    destination.write_bytes(contents)
    category = "CUSTOMER_MASTER" if master_type == "customer" else "PRODUCT_MASTER"
    try:
        with DB_LOCK, connect() as db:
            with db:
                cursor = db.execute(
                    "INSERT INTO managed_file(direction,category,original_name,stored_path,status,uploaded_by,created_at) "
                    "VALUES('INBOUND',?,?,?,'QUEUED',?,?)",
                    (category, name, str(destination), user["email"], utcnow().isoformat()),
                )
                row_id = int(cursor.lastrowid)
                audit(db, "master_file", str(row_id), "UPLOAD", user["email"],
                      after={"category": category, "filename": name})
    except sqlite3.Error:
        destination.unlink(missing_ok=True)
        raise
    return {"id": row_id, "filename": name, "status": "QUEUED", "queue_folder": "Inbound Queue"}


@router.get(f"{API_PREFIX}/admin/files")
async def managed_files(user: CurrentUser) -> dict[str, Any]:
    require_role(user, "ADMIN")
    with DB_LOCK, connect() as db:
        records = [
            dict(row)
            for row in db.execute(
                "SELECT id,direction,category,original_name,status,uploaded_by,created_at,"
                "processed_at,row_count,message FROM managed_file ORDER BY id DESC LIMIT 500"
            )
        ]
    return {"files": records}


@router.post(f"{API_PREFIX}/admin/files/{{file_id}}/process")
async def process_queued_master_file(file_id: int, user: CurrentUser) -> dict[str, Any]:
    require_role(user, "ADMIN")
    return process_master_file(file_id, user["email"])


@router.get(f"{API_PREFIX}/admin/files/{{file_id}}/download")
async def download_managed_file(file_id: int, user: CurrentUser) -> Response:
    require_role(user, "ADMIN")
    with DB_LOCK, connect() as db:
        record = db.execute("SELECT * FROM managed_file WHERE id=?", (file_id,)).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    stored = Path(record["stored_path"]).resolve()
    allowed_roots = [INBOUND_QUEUE_DIR.resolve(), INBOUND_PROCESSED_DIR.resolve(), OUTBOUND_DIR.resolve()]
    if not any(stored.parent == root for root in allowed_roots) or not stored.is_file():
        raise HTTPException(status_code=404, detail="File is not available")
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if stored.suffix == ".xlsx" else "text/csv"
    return Response(
        stored.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{record["original_name"]}"'},
    )
