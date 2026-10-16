"""Shared planning queries (products for a plan account)."""

from __future__ import annotations

import sqlite3


def product_rows_for_account(
    db: sqlite3.Connection, market: str, customer_id: int, include_approved: bool = True
) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT DISTINCT p.code,p.description,p.brand,p.sub_brand,p.category
        FROM product_p09 p
        WHERE p.active=1 AND (
          EXISTS(SELECT 1 FROM listing l WHERE l.market_code=? AND l.customer_id=? AND l.p09_code=p.code)
          OR (?=1 AND EXISTS(
            SELECT 1 FROM promotion pr JOIN promotion_item pi ON pi.promotion_id=pr.id
            WHERE pr.market_code=? AND pr.customer_id=? AND pr.status='APPROVED' AND pi.p09_code=p.code
          ))
        )
        ORDER BY p.brand,p.description
        """,
        (market, customer_id, int(include_approved), market, customer_id),
    ).fetchall()
