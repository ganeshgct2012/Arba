"""Application settings, file paths and demo master data constants."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

APP_TITLE = "ArBa Promo Volume Predictor"


API_PREFIX = "/api/v1"


MARKETS = (
    ("DE", "Germany", "VOL", "DE10"),
    ("ES", "Spain", "VOL", "ES10"),
    ("PT", "Portugal", "VOL", "PT10"),
    ("CH", "Switzerland", "PROMO", "CH10"),
    ("NL", "Netherlands", "PROMO", "NL10"),
    ("AT", "Austria", "PROMO", "AT10"),
    ("BE", "Belgium", "PROMO", "BE10"),
)


ACCOUNTS = (
    ("ROSSMANN", "Rossmann"),
    ("KAUFLAND", "Kaufland"),
    ("AMAZON", "Amazon"),
    ("EDEKA-NORD", "Edeka Nord"),
    ("NORMA", "Norma"),
    ("MUELLER", "Müller"),
)


PRODUCTS = (
    (
        "P09-1001",
        "Kleenex Facial Tissues 3-ply",
        "Kleenex",
        "Original",
        "Facial Tissue",
        2,
    ),
    ("P09-1002", "Kleenex Balsam Tissues", "Kleenex", "Balsam", "Facial Tissue", 1),
    (
        "P09-1003",
        "Kleenex Ultra Soft Pocket",
        "Kleenex",
        "Ultra Soft",
        "Pocket Tissue",
        3,
    ),
    (
        "P09-1004",
        "Kleenex Collection Cube",
        "Kleenex",
        "Collection",
        "Facial Tissue",
        1,
    ),
    (
        "P09-2001",
        "Scottex Original Toilet Tissue",
        "Scottex",
        "Original",
        "Toilet Tissue",
        2,
    ),
    (
        "P09-2002",
        "Scottex Sensitive Toilet Tissue",
        "Scottex",
        "Sensitive",
        "Toilet Tissue",
        1,
    ),
    ("P09-2003", "Scottex Fresh Toilet Tissue", "Scottex", "Fresh", "Toilet Tissue", 3),
    ("P09-3001", "Hakle Classic Toilet Tissue", "Hakle", "Classic", "Toilet Tissue", 1),
    ("P09-3002", "Hakle Naturel Toilet Tissue", "Hakle", "Naturel", "Toilet Tissue", 2),
    ("P09-3003", "Hakle Feucht Fresh", "Hakle", "Feucht", "Moist Tissue", 1),
    ("P09-4001", "Huggies Extra Care Size 3", "Huggies", "Extra Care", "Diapers", 2),
    ("P09-4002", "Huggies Extra Care Size 4", "Huggies", "Extra Care", "Diapers", 1),
    ("P09-4003", "Huggies Little Swimmers", "Huggies", "Swimmers", "Swim Pants", 3),
    ("P09-4004", "Huggies Baby Wipes Pure", "Huggies", "Pure", "Baby Wipes", 2),
    (
        "P09-4005",
        "Huggies Baby Wipes Natural",
        "Huggies",
        "Natural Care",
        "Baby Wipes",
        1,
    ),
)


TACTICS = ("Feature", "Display", "Price Promotion", "Coupon")


PIPELINES = (
    (
        "IN-01",
        "S/4 Customer Master",
        "INBOUND",
        "SAP S/4HANA",
        "ArBa",
        "MockSapConnector",
    ),
    (
        "IN-02",
        "S/4 Product Master",
        "INBOUND",
        "SAP S/4HANA",
        "ArBa",
        "MockSapConnector",
    ),
    (
        "IN-03",
        "S/4 Sell-in Actuals",
        "INBOUND",
        "SAP S/4HANA",
        "ArBa",
        "MockSapConnector",
    ),
    (
        "IN-04",
        "P09 to P10 Split Recalculation",
        "INBOUND",
        "ArBa Actuals",
        "ArBa",
        "MockSapConnector",
    ),
    (
        "OUT-01",
        "ArBa Weekly Volume Feed",
        "OUTBOUND",
        "ArBa",
        "P10 Arete",
        "MockP10Connector",
    ),
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


logger = logging.getLogger("arba")


PROJECT_ROOT = Path(__file__).resolve().parents[2]


DB_PATH = Path(os.getenv("ARBA_DB_PATH", PROJECT_ROOT / "data" / "arba_volume_planner.sqlite3"))


FILE_ROOT = Path(os.getenv("ARBA_FILES_DIR", DB_PATH.parent / "arba_files"))


INBOUND_QUEUE_DIR = FILE_ROOT / "Inbound Queue"


INBOUND_PROCESSED_DIR = FILE_ROOT / "Inbound Processed"


OUTBOUND_DIR = FILE_ROOT / "Outbound"


SIGNING_SECRET = os.getenv("ARBA_SECRET", "")


if not SIGNING_SECRET:
    SIGNING_SECRET = secrets.token_urlsafe(48)


SSO_STATE_COOKIE = "arba_sso_state"


SSO_SCOPES = "openid profile email User.Read"


FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
