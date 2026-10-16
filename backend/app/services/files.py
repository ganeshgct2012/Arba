"""Inbound/outbound file locations and storage of generated files."""

from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from fastapi import HTTPException

from app.config import FILE_ROOT, INBOUND_QUEUE_DIR, OUTBOUND_DIR
from app.db import DB_LOCK, connect
from app.services.audit import audit
from app.utils import utcnow


def configured_pipeline_path(value: str | None) -> Path | None:
    if value is None or not value.strip():
        return None
    root = FILE_ROOT.resolve()
    supplied = Path(value.strip())
    if supplied.is_absolute():
        raise HTTPException(status_code=422, detail="Pipeline file location must be relative to ArBa Files")
    resolved = (root / supplied).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Pipeline file location must stay within ArBa Files") from exc
    return resolved


def validate_pipeline_file_location(value: str | None, direction: str) -> Path | None:
    resolved = configured_pipeline_path(value)
    if resolved is None:
        return None
    expected_parent = (INBOUND_QUEUE_DIR if direction == "INBOUND" else OUTBOUND_DIR).resolve()
    if resolved.parent != expected_parent:
        folder = "Inbound Queue" if direction == "INBOUND" else "Outbound"
        raise HTTPException(
            status_code=422,
            detail=f"{direction} pipeline files must be directly inside the {folder} folder",
        )
    return resolved


def store_outbound_file(filename: str, category: str, contents: bytes, user_email: str) -> None:
    OUTBOUND_DIR.mkdir(parents=True, exist_ok=True)
    stored = OUTBOUND_DIR / f"{secrets.token_hex(8)}_{Path(filename).name}"
    stored.write_bytes(contents)
    try:
        with DB_LOCK, connect() as db:
            with db:
                cursor = db.execute(
                    "INSERT INTO managed_file(direction,category,original_name,stored_path,status,uploaded_by,created_at,row_count,message) "
                    "VALUES('OUTBOUND',?,?,?,'EXPORTED',?,?,0,'P10 export')",
                    (category, filename, str(stored), user_email, utcnow().isoformat()),
                )
                audit(db, "managed_file", str(cursor.lastrowid), "EXPORT", user_email,
                      after={"category": category, "filename": filename})
    except sqlite3.Error:
        stored.unlink(missing_ok=True)
        raise
