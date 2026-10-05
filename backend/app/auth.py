"""Per-user sessions. Demo sign-in is explicitly disabled in production mode."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import database

router = APIRouter(prefix="/api/auth", tags=["session"])
current_id: ContextVar[str | None] = ContextVar("creditwiz_user", default=None)
COOKIE = "creditwiz_session"
SESSION_SECONDS = 8 * 60 * 60


def production() -> bool:
    mode = os.environ.get("CREDITWIZ_ENV", "development").strip().lower()
    if mode not in {"development", "production"}:
        raise RuntimeError("CREDITWIZ_ENV must be development or production")
    return mode == "production"


def user_id() -> str:
    value = current_id.get()
    if not value:
        raise HTTPException(401, "Sign in to the MUFG AI Hub")
    return value


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()
    return f"{salt}:{digest}"


def seed_users() -> None:
    from .identity import _read

    with database.connect(write=True) as conn:
        if production():
            # Provision with the CLI or a configured bootstrap account. No demo bypass.
            if not conn.execute(
                "SELECT 1 FROM users WHERE password_hash != '' AND active=1"
            ).fetchone():
                email = os.environ.get("CREDITWIZ_BOOTSTRAP_EMAIL", "").strip().lower()
                password = os.environ.get("CREDITWIZ_BOOTSTRAP_PASSWORD", "")
                if not email or len(password) < 12:
                    raise RuntimeError(
                        "Provision a local account or configure CREDITWIZ_BOOTSTRAP_EMAIL and a password of at least 12 characters."
                    )
                profile = {
                    "id": "administrator",
                    "name": "Hub administrator",
                    "first_name": "Admin",
                    "initials": "AD",
                    "email": email,
                    "job_title": "Platform Engineer",
                    "groups": ["AI-Hub-Users", "AI-Hub-Admins"],
                }
                conn.execute(
                    "INSERT OR IGNORE INTO users(id,email,password_hash,profile) VALUES (?,?,?,?)",
                    (
                        profile["id"],
                        email,
                        password_hash(password),
                        json.dumps(profile),
                    ),
                )
                if not conn.execute(
                    "SELECT 1 FROM users WHERE password_hash != '' AND active=1"
                ).fetchone():
                    raise RuntimeError(
                        "Bootstrap account conflicts with existing data. Use app.manage user to provision an account."
                    )
        else:
            # Demo accounts are added when missing rather than only into an
            # empty database, so a new demo persona appears on an existing local
            # database, and a demo profile follows the code when it changes. The
            # directory account from user.json is left exactly as it is.
            base = _read("user.json")
            profiles = [base]
            for uid, name, role, dept, groups in (
                ("demo-business", "Alex Morgan", "Business Analyst", "Business", []),
                # The three desks of the design reference's demo data.
                (
                    "demo-rm",
                    "Rachel Donovan",
                    "Relationship Manager",
                    "Global Corporate Banking",
                    [],
                ),
                (
                    "demo-credit",
                    "Michael Barrett",
                    "Credit Analyst",
                    "Credit Underwriting, APAC",
                    [],
                ),
                (
                    "demo-compliance",
                    "Priya Shah",
                    "Compliance Analyst",
                    "Compliance",
                    ["KYC-Agent-User"],
                ),
                (
                    "demo-operations",
                    "Jordan Lee",
                    "Operations Analyst",
                    "Operations",
                    [],
                ),
                (
                    "demo-risk",
                    "Laura Whitman",
                    "Risk Analyst",
                    "Portfolio & Regulatory Risk",
                    [],
                ),
                (
                    "demo-developer",
                    "Taylor Chen",
                    "Data Engineer",
                    "Engineering",
                    ["AI-Builders"],
                ),
            ):
                profiles.append(
                    {
                        "id": uid,
                        "name": name,
                        "first_name": name.split()[0],
                        "initials": "".join(n[0] for n in name.split()),
                        "email": f"{uid}@mufg.example",
                        "job_title": role,
                        "department": dept,
                        "groups": ["AI-Hub-Users", *groups],
                    }
                )
            for profile in profiles:
                conn.execute(
                    "INSERT INTO users(id,email,profile) VALUES (?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET profile=excluded.profile "
                    "WHERE users.id LIKE 'demo-%'",
                    (profile["id"], profile["email"].lower(), json.dumps(profile)),
                )
            from .learning import progress

            progress.seed_demo(conn)


def resolve_session(token: str | None) -> str | None:
    if not token:
        return None
    with database.connect() as conn:
        row = conn.execute(
            "SELECT s.user_id FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    return row[0] if row else None


def start_session(uid: str, response: Response) -> dict:
    token = secrets.token_urlsafe(32)
    with database.connect(write=True) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (time.time(),))
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                uid,
                time.time() + SESSION_SECONDS,
            ),
        )
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=production(),
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.get("/options")
def options() -> dict:
    seed_users()
    with database.connect() as conn:
        profiles = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT profile FROM users WHERE active=1 ORDER BY id"
            )
        ]
    from . import entra

    return {
        "demo": not production(),
        # Whether "Sign in with Microsoft" can work: MUFG's app registration is configured.
        "microsoft": entra.configured(),
        "users": []
        if production()
        else [
            {"id": p["id"], "name": p["name"], "role": p.get("job_title", "")}
            for p in profiles
        ],
    }


class DemoLogin(BaseModel):
    user_id: str


@router.post("/demo")
def demo_login(body: DemoLogin, response: Response):
    if production():
        raise HTTPException(404)
    seed_users()
    with database.connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE id=? AND active=1", (body.user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(401, "Unknown demo account")
    return start_session(row[0], response)


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    seed_users()
    address = (
        f"{request.client.host if request.client else ''}|{body.email.strip().lower()}"
    )
    now = time.time()
    with database.connect(write=True) as conn:
        attempt = conn.execute(
            "SELECT * FROM login_attempts WHERE address=?", (address,)
        ).fetchone()
        if attempt and attempt["failures"] >= 5 and attempt["until_at"] > now:
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
        row = conn.execute(
            "SELECT * FROM users WHERE email=? AND active=1",
            (body.email.strip().lower(),),
        ).fetchone()
        stored = (
            row["password_hash"]
            if row and row["password_hash"]
            else password_hash("unavailable")
        )
        valid = (
            hmac.compare_digest(
                password_hash(body.password, stored.split(":")[0]), stored
            )
            and row
            and row["password_hash"]
        )
        if not valid:
            count = (
                attempt["failures"] + 1 if attempt and attempt["until_at"] > now else 1
            )
            conn.execute(
                "INSERT INTO login_attempts VALUES (?,?,?) ON CONFLICT(address) DO UPDATE SET failures=excluded.failures,until_at=excluded.until_at",
                (address, count, now + 900),
            )
        else:
            conn.execute("DELETE FROM login_attempts WHERE address=?", (address,))
    if not valid:
        raise HTTPException(401, "Email or password is incorrect")
    return start_session(row["id"], response)


@router.post("/logout")
def logout(request: Request, response: Response):
    from . import entra

    token = request.cookies.get(COOKIE, "")
    # Microsoft tokens go with the session.
    entra.forget(resolve_session(token))
    with database.connect(write=True) as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        )
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
