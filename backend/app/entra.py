"""Sign in with Microsoft Entra ID, and the tokens the hub calls Microsoft with.

The authorization code flow with PKCE, run on the server: the browser never
sees a token. Configure from MUFG's app registration:

    ENTRA_TENANT_ID       the directory (tenant) id
    ENTRA_CLIENT_ID       the application (client) id
    ENTRA_CLIENT_SECRET   a client secret for that application
    ENTRA_REDIRECT_URI    a redirect URI on the registration (Web platform);
                          defaults to the local address below

The registration needs these delegated permissions, consented for the tenant:
Microsoft Graph User.Read and Community.Read.All, and Viva Engage (Yammer)
user_impersonation.

Tokens are held in this process's memory against the hub user: never in the
database, a log or the browser. A restart means signing in again.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from . import auth, database, http

router = APIRouter(prefix="/api/auth/microsoft", tags=["session"])
SERVICE = "Microsoft Entra ID"
LOGIN = "https://login.microsoftonline.com"
GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPES = "https://graph.microsoft.com/User.Read https://graph.microsoft.com/Community.Read.All"
ENGAGE_SCOPES = "https://www.yammer.com/.default"
SIGN_IN_SCOPES = f"openid profile email offline_access {GRAPH_SCOPES}"
DEFAULT_REDIRECT = "http://localhost:5175/api/auth/microsoft/callback"
STATE_COOKIE = "creditwiz_entra_state"
PENDING_SECONDS = 600
Resource = Literal["graph", "engage"]
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def configured() -> bool:
    return all(_env(n) for n in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"))


def redirect_uri() -> str:
    return _env("ENTRA_REDIRECT_URI") or DEFAULT_REDIRECT


@dataclass
class _Grant:
    refresh_token: str
    tokens: dict[str, tuple[str, float]] = field(default_factory=dict)


_grants: dict[str, _Grant] = {}
# state -> (code verifier, nonce, where to go next, created at)
_pending: dict[str, tuple[str, str, str, float]] = {}
_lock = threading.Lock()


def signed_in(user_id: str | None) -> bool:
    with _lock:
        return bool(user_id) and user_id in _grants


def forget(user_id: str | None) -> None:
    with _lock:
        _grants.pop(user_id or "", None)


def _redeem(form: dict) -> dict:
    response = http.send(
        SERVICE,
        "POST",
        f"{LOGIN}/{_env('ENTRA_TENANT_ID')}/oauth2/v2.0/token",
        form={"client_id": _env("ENTRA_CLIENT_ID"), "client_secret": _env("ENTRA_CLIENT_SECRET"), **form},
    )
    data = response.json() or {}
    if "access_token" not in data:
        raise http.ExternalError(SERVICE, response.status, "Microsoft returned no access token.")
    return data


def token_for(user_id: str | None, resource: Resource) -> str | None:
    """An access token for Graph or Viva Engage, as this person; refreshed when it
    is about to expire. None when they have not signed in with Microsoft."""
    with _lock:
        grant = _grants.get(user_id or "")
        held = grant.tokens.get(resource) if grant else None
    if grant is None:
        return None
    if held and held[1] - 60 > time.time():
        return held[0]
    scopes = ENGAGE_SCOPES if resource == "engage" else GRAPH_SCOPES
    data = _redeem({"grant_type": "refresh_token", "refresh_token": grant.refresh_token, "scope": f"{scopes} offline_access"})
    with _lock:
        grant.tokens[resource] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        if data.get("refresh_token"):
            grant.refresh_token = data["refresh_token"]
    return data["access_token"]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def claims(id_token: str, nonce: str) -> dict:
    """The ID token's claims, checked.

    The token came straight from the token endpoint over TLS, in exchange for
    the client's secret, so OpenID Connect lets the hub rely on TLS for who
    issued it (OpenID Connect Core 3.1.3.7). Audience, tenant, nonce and expiry
    are checked here.
    """
    try:
        payload = id_token.split(".")[1]
        found = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise ValueError("Microsoft returned no readable ID token.") from None
    tenant = _env("ENTRA_TENANT_ID")
    if found.get("aud") != _env("ENTRA_CLIENT_ID"):
        raise ValueError("The ID token was issued for another application.")
    if _GUID.match(tenant) and found.get("tid") != tenant:
        raise ValueError("The ID token comes from another tenant.")
    if not hmac.compare_digest(str(found.get("nonce", "")), nonce):
        raise ValueError("The ID token's nonce does not match this sign-in.")
    if float(found.get("exp", 0)) < time.time():
        raise ValueError("The ID token has expired.")
    if not found.get("oid"):
        raise ValueError("The ID token carries no object id.")
    return found


def upsert_user(found: dict, me: dict) -> str:
    """The hub account for this Microsoft identity, created or brought up to date
    from the directory. Its persona follows from the job title and department."""
    uid = f"entra-{found['oid']}"
    name = me.get("displayName") or found.get("name") or "MUFG colleague"
    email = (me.get("mail") or me.get("userPrincipalName") or found.get("preferred_username") or f"{uid}@entra.invalid").lower()
    profile = {
        "id": uid,
        "name": name,
        "first_name": me.get("givenName") or name.split()[0],
        "initials": "".join(part[0] for part in name.split()[:2]).upper() or "MU",
        "email": email,
        "job_title": me.get("jobTitle") or "",
        "department": me.get("department") or "",
        "location": me.get("officeLocation") or "",
        # Every signed-in colleague is a hub user. Mapping Entra groups to the
        # hub's other groups is to be confirmed with MUFG.
        "groups": ["AI-Hub-Users"],
    }
    with database.connect(write=True) as conn:
        conn.execute(
            "INSERT INTO users(id,email,profile) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET email=excluded.email, profile=excluded.profile",
            (uid, email, json.dumps(profile)),
        )
    return uid


@router.get("/login")
def login(next: str = "/community"):
    if not configured():
        return RedirectResponse("/integrations?entra=not_configured", status_code=302)
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    now = time.time()
    with _lock:
        for old in [s for s, p in _pending.items() if now - p[3] > PENDING_SECONDS]:
            _pending.pop(old, None)
        _pending[state] = (verifier, nonce, target, now)
    query = urlencode(
        {
            "client_id": _env("ENTRA_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": redirect_uri(),
            "response_mode": "query",
            "scope": SIGN_IN_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{LOGIN}/{_env('ENTRA_TENANT_ID')}/oauth2/v2.0/authorize?{query}", status_code=302)
    response.set_cookie(
        STATE_COOKIE, state, max_age=PENDING_SECONDS, httponly=True, secure=auth.production(), samesite="lax", path="/api/auth/microsoft"
    )
    return response


@router.get("/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "", error_description: str = ""):
    from . import integrations

    def fail(reason: str) -> RedirectResponse:
        integrations.record_error("entra", auth.current_id.get(), reason)
        response = RedirectResponse("/integrations?entra=failed", status_code=302)
        response.delete_cookie(STATE_COOKIE, path="/api/auth/microsoft")
        return response

    if error:
        return fail(f"{SERVICE}: {(error_description or error).splitlines()[0][:300]}")
    with _lock:
        pending = _pending.pop(state, None) if state else None
    cookie = request.cookies.get(STATE_COOKIE, "")
    if not pending or not code or not hmac.compare_digest(state, cookie):
        return fail("The sign-in could not be verified. Start it again from the hub.")
    verifier, nonce, target, created = pending
    if time.time() - created > PENDING_SECONDS:
        return fail("The sign-in took too long. Start it again from the hub.")
    try:
        tokens = _redeem(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "code_verifier": verifier,
                "scope": SIGN_IN_SCOPES,
            }
        )
        found = claims(tokens.get("id_token", ""), nonce)
        me = http.send(
            SERVICE,
            "GET",
            f"{GRAPH}/me?$select=id,displayName,givenName,mail,userPrincipalName,jobTitle,department,officeLocation",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        ).json() or {}
        uid = upsert_user(found, me)
    except http.ExternalError as e:
        return fail(integrations.explain(e))
    except ValueError as e:
        return fail(str(e))
    except sqlite3.IntegrityError:
        return fail("Another hub account already uses this email address.")
    with _lock:
        _grants[uid] = _Grant(
            refresh_token=tokens.get("refresh_token", ""),
            tokens={"graph": (tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600)))},
        )
    integrations.clear_error("entra", uid)
    # Viva Engage takes a token of its own. Asking for it now shows a missing
    # permission on the Integrations page straight away, not on the first post.
    try:
        token_for(uid, "engage")
        integrations.clear_error("viva_engage", uid)
    except http.ExternalError as e:
        integrations.record_error("viva_engage", uid, integrations.explain(e))
    response = RedirectResponse(target, status_code=302)
    auth.start_session(uid, response)
    response.delete_cookie(STATE_COOKIE, path="/api/auth/microsoft")
    return response
