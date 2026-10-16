"""Minimal XLSX writer (no external dependencies)."""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from app.services.p10_feed import P10_COLUMNS


def xlsx_column(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def build_xlsx(
    rows: list[dict[str, str]], columns: tuple[str, ...] = P10_COLUMNS
) -> bytes:
    spreadsheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    office_rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ET.register_namespace("", spreadsheet_ns)
    ET.register_namespace("r", office_rel_ns)
    worksheet = ET.Element(f"{{{spreadsheet_ns}}}worksheet")
    sheet_data = ET.SubElement(worksheet, f"{{{spreadsheet_ns}}}sheetData")
    records = [list(columns), *[[row[column] for column in columns] for row in rows]]
    for row_number, values in enumerate(records, start=1):
        xml_row = ET.SubElement(sheet_data, f"{{{spreadsheet_ns}}}row", {"r": str(row_number)})
        for column_number, value in enumerate(values, start=1):
            cell = ET.SubElement(
                xml_row,
                f"{{{spreadsheet_ns}}}c",
                {"r": f"{xlsx_column(column_number)}{row_number}", "t": "inlineStr"},
            )
            inline = ET.SubElement(cell, f"{{{spreadsheet_ns}}}is")
            text = ET.SubElement(inline, f"{{{spreadsheet_ns}}}t")
            text.text = str(value)

    workbook = ET.Element(f"{{{spreadsheet_ns}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{spreadsheet_ns}}}sheets")
    ET.SubElement(
        sheets,
        f"{{{spreadsheet_ns}}}sheet",
        {
            "name": "Sheet1",
            "sheetId": "1",
            f"{{{office_rel_ns}}}id": "rId1",
        },
    )

    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": ET.tostring(workbook, encoding="unicode", xml_declaration=True),
        "xl/worksheets/sheet1.xml": ET.tostring(
            worksheet, encoding="unicode", xml_declaration=True
        ),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()
