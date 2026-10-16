"""Microsoft Entra ID (Azure AD) single sign-on helpers."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from app.config import logger


class SSOAuthenticationError(Exception):
    pass


def entra_sso_config() -> dict[str, str] | None:
    required = {
        "tenant_id": os.getenv("ARBA_ENTRA_TENANT_ID", "").strip(),
        "client_id": os.getenv("ARBA_ENTRA_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("ARBA_ENTRA_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("ARBA_ENTRA_REDIRECT_URI", "").strip(),
    }
    if not all(required.values()):
        return None
    return required


def sso_http_json(url: str, data: dict[str, str] | None = None, access_token: str | None = None) -> Any:
    body = urlencode(data).encode() if data is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = URLRequest(url, data=body, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Entra SSO request failed: %s", type(exc).__name__)
        raise SSOAuthenticationError("The identity provider could not complete sign-in") from exc
