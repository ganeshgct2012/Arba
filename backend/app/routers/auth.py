"""Login, signup, logout, current user and Entra SSO endpoints."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.config import API_PREFIX, SSO_SCOPES, SSO_STATE_COOKIE, logger
from app.db import DB_LOCK, connect
from app.deps import CurrentUser
from app.schemas import LoginPayload, SignupPayload
from app.security import (
    password_hash,
    set_session_cookie,
    sign_session,
    signed_sso_state,
    verify_password,
    verify_sso_state,
)
from app.services.audit import audit
from app.services.sso import SSOAuthenticationError, entra_sso_config, sso_http_json
from app.utils import utcnow

router = APIRouter(tags=['auth'])


@router.post(f"{API_PREFIX}/auth/login")
async def login(payload: LoginPayload, response: Response) -> dict[str, Any]:
    with DB_LOCK, connect() as db:
        with db:
            row = db.execute(
                "SELECT * FROM app_user WHERE email=? COLLATE NOCASE",
                (payload.email.strip().lower(),),
            ).fetchone()
            authenticated = (
                row is not None
                and bool(row["active"])
                and verify_password(payload.password, row["password_hash"])
            )
            if authenticated:
                db.execute(
                    "UPDATE app_user SET last_login_at=? WHERE id=?",
                    (utcnow().isoformat(), row["id"]),
                )
                row = db.execute("SELECT * FROM app_user WHERE id=?", (row["id"],)).fetchone()
                admin_sales_org_access = [
                    item["sales_org"]
                    for item in db.execute(
                        "SELECT sales_org FROM user_sales_org_admin WHERE user_id=? ORDER BY sales_org",
                        (row["id"],),
                    )
                ]
            else:
                admin_sales_org_access = []
    if not authenticated or row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    expiry = int((utcnow() + timedelta(hours=10)).timestamp())
    cookie = sign_session(int(row["id"]), row["role"], expiry)
    response.set_cookie(
        "arba_session",
        cookie,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ARBA_COOKIE_SECURE", "0") == "1",
        max_age=10 * 60 * 60,
    )
    return {
        "user": {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "role": row["role"],
            "admin_sales_org_access": admin_sales_org_access,
        }
    }


@router.post(f"{API_PREFIX}/auth/signup", status_code=201)
async def signup(payload: SignupPayload, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must contain at least 2 characters")
    hashed_password = password_hash(payload.password)
    with DB_LOCK, connect() as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM app_user WHERE email=? COLLATE NOCASE", (email,)
            ).fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists. Sign in or contact an administrator.",
                )
            first_user_admin = (
                db.execute("SELECT 1 FROM app_user WHERE is_seed=0 LIMIT 1").fetchone() is None
            )
            role = "ADMIN" if first_user_admin else "VIEWER"
            cursor = db.execute(
                "INSERT INTO app_user(email,name,role,password_hash,is_seed,last_login_at) "
                "VALUES(?,?,?,?,0,?)",
                (email, name, role, hashed_password, utcnow().isoformat()),
            )
            user_id = int(cursor.lastrowid)
            audit(
                db,
                "app_user",
                str(user_id),
                "SIGN_UP",
                email,
                after={"role": role},
            )
            row = db.execute(
                "SELECT id,email,name,role FROM app_user WHERE id=?", (user_id,)
            ).fetchone()
    set_session_cookie(response, int(row["id"]), str(row["role"]))
    return {"user": dict(row), "first_user_admin": first_user_admin}


@router.get(f"{API_PREFIX}/auth/sso/status")
async def sso_status() -> dict[str, Any]:
    return {"enabled": entra_sso_config() is not None, "provider": "Microsoft Entra ID"}


@router.get(f"{API_PREFIX}/auth/sso/start")
async def sso_start() -> Response:
    config = entra_sso_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="SSO is not configured. Set the ARBA_ENTRA_* environment variables.",
        )
    try:
        tenant_id = str(UUID(config["tenant_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="ARBA_ENTRA_TENANT_ID must be a tenant UUID") from exc
    redirect_uri = config["redirect_uri"]
    parsed_redirect_uri = urlsplit(redirect_uri)
    is_local_http = parsed_redirect_uri.scheme == "http" and parsed_redirect_uri.hostname in {
        "localhost",
        "127.0.0.1",
    }
    if (
        parsed_redirect_uri.scheme != "https" and not is_local_http
    ) or not parsed_redirect_uri.netloc or parsed_redirect_uri.fragment or parsed_redirect_uri.username:
        raise HTTPException(
            status_code=500,
            detail="ARBA_ENTRA_REDIRECT_URI must use HTTPS (HTTP is allowed only for local development)",
        )

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    authorize_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    query = urlencode(
        {
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": SSO_SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{authorize_url}?{query}", status_code=302)
    response.set_cookie(
        SSO_STATE_COOKIE,
        signed_sso_state(state, verifier),
        httponly=True,
        samesite="lax",
        secure=os.getenv("ARBA_COOKIE_SECURE", "0") == "1",
        max_age=600,
        path=f"{API_PREFIX}/auth/sso",
    )
    return response


@router.get(f"{API_PREFIX}/auth/sso/callback")
async def sso_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    response: Response
    if error:
        result = "cancelled" if error == "access_denied" else "failed"
        response = RedirectResponse(f"/?sso_error={result}", status_code=303)
        response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
        return response
    verifier = verify_sso_state(request.cookies.get(SSO_STATE_COOKIE), state or "")
    config = entra_sso_config()
    if not code or verifier is None or config is None:
        response = RedirectResponse("/?sso_error=invalid_state", status_code=303)
        response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
        return response
    try:
        tenant_id = str(UUID(config["tenant_id"]))
    except ValueError:
        response = RedirectResponse("/?sso_error=configuration", status_code=303)
        response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
        return response

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    try:
        tokens = await asyncio.to_thread(
            sso_http_json,
            token_url,
            {
                "grant_type": "authorization_code",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
                "code_verifier": verifier,
                "scope": SSO_SCOPES,
            },
        )
        access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise SSOAuthenticationError("The identity provider did not return an access token")
        profile = await asyncio.to_thread(
            sso_http_json,
            "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
            None,
            access_token,
        )
        if not isinstance(profile, dict):
            raise SSOAuthenticationError("The identity provider returned an invalid profile")
    except SSOAuthenticationError:
        logger.warning("Microsoft Entra SSO authentication failed")
        response = RedirectResponse("/?sso_error=authentication_failed", status_code=303)
        response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
        return response

    subject = profile.get("id")
    email = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
    name = str(profile.get("displayName") or email.split("@", maxsplit=1)[0]).strip()
    if not isinstance(subject, str) or not subject or email.count("@") != 1 or not name:
        response = RedirectResponse("/?sso_error=profile_incomplete", status_code=303)
        response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
        return response
    sso_subject = f"entra:{tenant_id}:{subject}"

    with DB_LOCK, connect() as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id,email,name,role,active FROM app_user WHERE sso_subject=?",
                (sso_subject,),
            ).fetchone()
            created = row is None
            if row is None:
                email_row = db.execute(
                    "SELECT id FROM app_user WHERE email=? COLLATE NOCASE", (email,)
                ).fetchone()
                if email_row:
                    response = RedirectResponse("/?sso_error=account_exists", status_code=303)
                    response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
                    return response
                first_user_admin = (
                    db.execute("SELECT 1 FROM app_user WHERE is_seed=0 LIMIT 1").fetchone() is None
                )
                role = "ADMIN" if first_user_admin else "VIEWER"
                cursor = db.execute(
                    "INSERT INTO app_user(email,name,role,password_hash,sso_subject) "
                    "VALUES(?,?,?,?,?)",
                    (email, name, role, password_hash(secrets.token_urlsafe(32)), sso_subject),
                )
                user_id = int(cursor.lastrowid)
                row = db.execute(
                    "SELECT id,email,name,role,active FROM app_user WHERE id=?", (user_id,)
                ).fetchone()
                audit(db, "app_user", str(user_id), "SSO_SIGN_UP", email, after={"role": role})
            if row is None or not row["active"]:
                response = RedirectResponse("/?sso_error=account_inactive", status_code=303)
                response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
                return response
            db.execute(
                "UPDATE app_user SET last_login_at=? WHERE id=?",
                (utcnow().isoformat(), row["id"]),
            )
            row = db.execute(
                "SELECT id,email,name,role,active FROM app_user WHERE id=?", (row["id"],)
            ).fetchone()

    sso_result = (
        "created_admin" if created and first_user_admin else "created"
    ) if created else "signed_in"
    response = RedirectResponse(f"/?sso={sso_result}", status_code=303)
    set_session_cookie(response, int(row["id"]), str(row["role"]))
    response.delete_cookie(SSO_STATE_COOKIE, path=f"{API_PREFIX}/auth/sso")
    return response


@router.post(f"{API_PREFIX}/auth/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("arba_session", httponly=True, samesite="lax")
    return {"status": "signed out"}


@router.get(f"{API_PREFIX}/auth/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    return user
