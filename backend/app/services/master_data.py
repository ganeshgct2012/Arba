"""Customer / product master CSV-XLSX parsing and loading."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
import zipfile
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from app.config import INBOUND_PROCESSED_DIR, INBOUND_QUEUE_DIR
from app.db import DB_LOCK, connect
from app.services.audit import audit
from app.utils import utcnow


def master_file_rows(filename: str, contents: bytes) -> list[tuple[int, dict[str, str]]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding") from exc
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("The file must contain a header row")
        return [
            (row_number, {re.sub(r"[^a-z0-9]", "", (key or "").lower()): (value or "").strip()
                          for key, value in row.items() if key})
            for row_number, row in enumerate(reader, start=2)
            if any(value and value.strip() for value in row.values() if value is not None)
        ]
    if suffix != ".xlsx":
        raise ValueError("Upload a CSV or XLSX file")
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 50_000_000:
                raise ValueError("Expanded XLSX file is too large")
            names = set(archive.namelist())
            if "xl/worksheets/sheet1.xml" not in names:
                raise ValueError("The XLSX workbook does not contain Sheet1")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [
                    "".join(node.text or "" for node in item.iter()
                            if node.tag.endswith("}t") or node.tag == "t")
                    for item in shared_root
                ]
            root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            grid: list[list[str]] = []
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                values: dict[int, str] = {}
                for cell in row:
                    if not cell.tag.endswith("}c"):
                        continue
                    cell_ref = cell.attrib.get("r", "")
                    letters = re.match(r"[A-Z]+", cell_ref)
                    if not letters:
                        continue
                    column = 0
                    for character in letters.group():
                        column = column * 26 + ord(character) - 64
                    cell_type = cell.attrib.get("t")
                    value_node = next((part for part in cell if part.tag.endswith("}v")), None)
                    if cell_type == "inlineStr":
                        value = "".join(
                            part.text or ""
                            for part in cell.iter()
                            if part.tag.endswith("}t")
                        )
                    elif value_node is None or value_node.text is None:
                        value = ""
                    elif cell_type == "s":
                        value = shared[int(value_node.text)]
                    else:
                        value = value_node.text
                    values[column - 1] = value.strip()
                if values:
                    grid.append([values.get(index, "") for index in range(max(values) + 1)])
    except (zipfile.BadZipFile, ET.ParseError, IndexError, KeyError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Unable to read the XLSX workbook; export a valid .xlsx file") from exc
    if not grid or not grid[0]:
        raise ValueError("The workbook must contain a header row on its first sheet")
    headers = [re.sub(r"[^a-z0-9]", "", header.lower()) for header in grid[0]]
    return [
        (row_number, dict(zip(headers, values)))
        for row_number, values in enumerate(grid[1:], start=2)
        if any(value for value in values)
    ]


def required_master_value(row: dict[str, str], *headers: str) -> str:
    for header in headers:
        value = row.get(re.sub(r"[^a-z0-9]", "", header.lower()), "")
        if value:
            return value.strip()
    raise ValueError(f"Missing required column/value: {headers[0]}")


def fail_managed_file(file_id: int, message: str) -> None:
    with DB_LOCK, connect() as db:
        db.execute(
            "UPDATE managed_file SET status='FAILED',processed_at=?,message=? WHERE id=?",
            (utcnow().isoformat(), message[:1000], file_id),
        )


def apply_customer_master(db: sqlite3.Connection, data: list[tuple[int, dict[str, str]]]) -> int:
    rows: list[tuple[int, str, str, str, str | None]] = []
    markets = {row["code"] for row in db.execute("SELECT code FROM market WHERE active=1")}
    for row_number, row in data:
        try:
            market = required_master_value(
                row, "Market Code", "Market", "Sales Organization", "Sales Org"
            )
            if market not in markets:
                market_row = db.execute(
                    "SELECT code FROM market WHERE p10_sales_org=? AND active=1", (market,)
                ).fetchone()
                if market_row:
                    market = str(market_row["code"])
            external_code = required_master_value(
                row,
                "Plan Account Code L04",
                "Plan Account L04",
                "Customer L04",
                "Customer ID",
                "Customer Number",
                "Account Code",
            )
            name = required_master_value(row, "Plan Account Name", "Customer Name", "Name")
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {exc}") from exc
        if market not in markets:
            raise ValueError(f"Row {row_number}: unknown or inactive market {market}")
        parent = next(
            (value for key, value in row.items() if key in {"parentl03", "customerl03", "l03"}),
            "",
        )
        rows.append((row_number, market, external_code, name, parent or None))
    if not rows:
        raise ValueError("The customer master file contains no data rows")
    for _, market, external_code, name, parent in rows:
        existing = db.execute(
            "SELECT id FROM customer_l04 WHERE market_code=? AND "
            "(external_code=? OR (external_code IS NULL AND name=?)) LIMIT 1",
            (market, external_code, name),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE customer_l04 SET name=?,parent_l03=?,external_code=?,active=1,source_updated_at=? WHERE id=?",
                (name, parent, external_code, utcnow().isoformat(), existing["id"]),
            )
        else:
            db.execute(
                "INSERT INTO customer_l04(market_code,name,parent_l03,external_code,source_updated_at) "
                "VALUES(?,?,?,?,?)",
                (market, name, parent, external_code, utcnow().isoformat()),
            )
    return len(rows)


def ensure_product_hierarchy(db: sqlite3.Connection, code: str, description: str,
                             brand: str, sub_brand: str, category: str) -> str:
    path = [brand, sub_brand, category, "All Products", "All Products", "All Products",
            "All Products", "All Products"]
    parent: str | None = None
    for level, text in enumerate(path, start=1):
        identity = hashlib.sha256(f"{level}|{parent}|{text}".encode()).hexdigest()[:18]
        node_id = f"SAP-P{level}-{identity}"
        db.execute(
            "INSERT INTO product_hierarchy(node_id,parent_id,level,code,text) VALUES(?,?,?,?,?) "
            "ON CONFLICT(node_id) DO UPDATE SET text=excluded.text",
            (node_id, parent, level, text, text),
        )
        parent = node_id
    db.execute(
        "INSERT INTO product_hierarchy(node_id,parent_id,level,code,text) VALUES(?,?,9,?,?) "
        "ON CONFLICT(node_id) DO UPDATE SET parent_id=excluded.parent_id,text=excluded.text",
        (code, parent, code, description),
    )
    return code


def apply_product_master(db: sqlite3.Connection, data: list[tuple[int, dict[str, str]]]) -> int:
    rows: list[tuple[int, str, str, str, str, str, str, str, float | None]] = []
    for row_number, row in data:
        try:
            code = required_master_value(row, "Product P09", "P09 Code", "P09")
            description = required_master_value(row, "Product Description", "P09 Description", "Description")
            brand = required_master_value(row, "Brand")
            material = required_master_value(row, "Material Number", "P10 Material", "Material P10")
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: {exc}") from exc
        sub_brand = next((value for key, value in row.items() if key in {"subbrand", "subbrandname"}), "") or brand
        category = next((value for key, value in row.items() if key in {"category", "productcategory"}), "") or "Uncategorized"
        material_description = next((value for key, value in row.items() if key in {"materialdescription", "p10description"}), "") or description
        share_text = next((value for key, value in row.items() if key in {"splitshare", "share"}), "")
        try:
            share = float(share_text) if share_text else None
        except ValueError as exc:
            raise ValueError(f"Row {row_number}: split share must be numeric") from exc
        if share is not None and not 0 <= share <= 100:
            raise ValueError(f"Row {row_number}: split share must be between 0 and 100")
        rows.append((row_number, code, description, brand, sub_brand, category, material, material_description, share))
    if not rows:
        raise ValueError("The product master file contains no data rows")
    material_shares: dict[str, dict[str, float]] = {}
    products_with_share: set[str] = set()
    for row_number, code, description, brand, sub_brand, category, material, material_description, share in rows:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,50}", code):
            raise ValueError(f"Row {row_number}: invalid P09 product code")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,50}", material):
            raise ValueError(f"Row {row_number}: invalid P10 material number")
        if share is not None:
            products_with_share.add(code)
            if material in material_shares.setdefault(code, {}):
                raise ValueError(f"Row {row_number}: duplicate P10 material {material} with split shares")
            material_shares[code][material] = share
        node = ensure_product_hierarchy(db, code, description, brand, sub_brand, category)
        db.execute(
            "INSERT INTO product_p09(code,description,brand,sub_brand,category,hierarchy_node_id,active) "
            "VALUES(?,?,?,?,?,?,1) ON CONFLICT(code) DO UPDATE SET description=excluded.description,"
            "brand=excluded.brand,sub_brand=excluded.sub_brand,category=excluded.category,"
            "hierarchy_node_id=excluded.hierarchy_node_id,active=1",
            (code, description, brand, sub_brand, category, node),
        )
        owner = db.execute("SELECT p09_code FROM material_p10 WHERE material=?", (material,)).fetchone()
        if owner and owner["p09_code"] != code:
            raise ValueError(f"Row {row_number}: P10 material {material} is assigned to another P09")
        db.execute(
            "INSERT INTO material_p10(material,description,p09_code,case_uom,active) VALUES(?,?,?,'CS',1) "
            "ON CONFLICT(material) DO UPDATE SET description=excluded.description,p09_code=excluded.p09_code,active=1",
            (material, material_description, code),
        )
    for code in {row[1] for row in rows}:
        materials = [
            row["material"]
            for row in db.execute(
                "SELECT material FROM material_p10 WHERE p09_code=? AND active=1 ORDER BY material",
                (code,),
            )
        ]
        if code in products_with_share:
            supplied = material_shares[code]
            if set(supplied) != set(materials):
                raise ValueError(f"Product {code}: provide split shares for every active P10 material or none")
            total = sum(supplied.values())
            if abs(total - 100) > 0.01:
                raise ValueError(f"Product {code}: supplied material shares must total 100% (got {total:g}%)")
            for material, share in supplied.items():
                db.execute(
                    "INSERT INTO p09_p10_split(p09_code,material,share,valid_from,source) "
                    "VALUES(?,?,?,?,'MANUAL') ON CONFLICT(p09_code,material,valid_from) "
                    "DO UPDATE SET share=excluded.share,source='MANUAL'",
                    (code, material, share, date.today().isoformat()),
                )
            continue
        manual_shares: dict[str, float] = {}
        for row in db.execute(
            "SELECT material,share FROM p09_p10_split WHERE p09_code=? AND source='MANUAL' "
            "AND valid_from<=? ORDER BY valid_from DESC",
            (code, date.today().isoformat()),
        ):
            manual_shares.setdefault(row["material"], float(row["share"]))
        manual_total = sum(manual_shares.values())
        remaining = [material for material in materials if material not in manual_shares]
        if manual_total > 100.01 or (not remaining and manual_total < 99.99):
            raise ValueError(f"Product {code}: existing manual material shares must total 100%")
        calculated_share = (100 - manual_total) / len(remaining) if remaining else 0
        for material in remaining:
            db.execute(
                "INSERT INTO p09_p10_split(p09_code,material,share,valid_from,source) "
                "VALUES(?,?,?,?,'CALC') ON CONFLICT(p09_code,material,valid_from) "
                "DO UPDATE SET share=excluded.share,source='CALC'",
                (code, material, calculated_share, date.today().isoformat()),
            )
    return len(rows)


def process_master_file(file_id: int, user_email: str) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        record = db.execute("SELECT * FROM managed_file WHERE id=?", (file_id,)).fetchone()
        if record is None:
            raise HTTPException(status_code=404, detail="File not found")
        if record["direction"] != "INBOUND" or record["status"] not in {"QUEUED", "FAILED"}:
            raise HTTPException(status_code=409, detail="Only queued or failed inbound files can be processed")
        with db:
            db.execute(
                "UPDATE managed_file SET status='PROCESSING',message=NULL WHERE id=?",
                (file_id,),
            )
        source = Path(record["stored_path"])
        if source.parent.resolve() != INBOUND_QUEUE_DIR.resolve() or not source.is_file():
            raise HTTPException(status_code=404, detail="Queued file is missing from the inbound queue")
        filename = record["original_name"]
        category = record["category"]
        file_bytes = source.read_bytes()
        try:
            data = master_file_rows(filename, file_bytes)
            with db:
                count = (
                    apply_customer_master(db, data)
                    if category == "CUSTOMER_MASTER"
                    else apply_product_master(db, data)
                )
                db.execute(
                    "UPDATE managed_file SET row_count=?,message=? WHERE id=?",
                    (count, f"Validated and applied {count} rows", file_id),
                )
                audit(db, "master_file", str(file_id), "PROCESS", user_email,
                      after={"category": category, "rows": count})
        except ValueError as exc:
            message = str(exc)
            fail_managed_file(file_id, message)
            raise HTTPException(status_code=422, detail=message) from exc
        except sqlite3.IntegrityError as exc:
            message = "The extract contains a master-data row that conflicts with existing records"
            fail_managed_file(file_id, message)
            raise HTTPException(status_code=422, detail=message) from exc
        destination = INBOUND_PROCESSED_DIR / source.name
        source.replace(destination)
        with db:
            db.execute(
                "UPDATE managed_file SET stored_path=?,status='PROCESSED',processed_at=? WHERE id=?",
                (str(destination), utcnow().isoformat(), file_id),
            )
    return {"id": file_id, "status": "PROCESSED", "rows": count}
