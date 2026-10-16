"""Audit log and promotion status history writers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.utils import utcnow


def audit(
    db: sqlite3.Connection,
    entity: str,
    entity_id: str,
    action: str,
    user: str,
    before: Any = None,
    after: Any = None,
) -> None:
    db.execute(
        "INSERT INTO audit_log(entity,entity_id,action,user,ts,before_json,after_json) VALUES(?,?,?,?,?,?,?)",
        (
            entity,
            entity_id,
            action,
            user,
            utcnow().isoformat(),
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
        ),
    )


def log_status(db: sqlite3.Connection, promo_id: int, user: str, old: str | None, new: str) -> None:
    db.execute(
        "INSERT INTO promotion_status_log(promotion_id,ts,user,old_status,new_status) VALUES(?,?,?,?,?)",
        (promo_id, utcnow().isoformat(), user, old, new),
    )
