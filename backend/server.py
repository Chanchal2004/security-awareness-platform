from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import re
import io
import csv
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, StreamingResponse, Response as FastResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from db import db
from security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    get_current_user, require_admin,
)
from email_service import send_email, assert_safe_email, EMAIL_FROM_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("talbros")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
APP_NAME = "TALBROS Security Awareness Center"



app = FastAPI(title=APP_NAME)



api = APIRouter(prefix="/api")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.I)

EVENT_TYPES = [
    "EMAIL_SENT", "EMAIL_DELIVERED", "EMAIL_OPENED", "LINK_CLICKED",
    "LANDING_PAGE_VISITED", "FORM_STARTED", "FORM_SUBMITTED",
]
SIM_STATUSES = ["DRAFT", "SCHEDULED", "RUNNING", "COMPLETED", "PAUSED", "CANCELLED"]

# 1x1 transparent PNG
PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


async def log_audit(admin_email: str, action: str, object_id: Optional[str] = None, details: str = ""):
    await db.audit_logs.insert_one({
        "id": new_id(), "admin_email": admin_email, "action": action,
        "object_id": object_id, "details": details, "timestamp": now_iso(),
    })


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginBody(BaseModel):
    email: EmailStr
    password: str


def set_auth_cookies(response: Response, user_id: str, email: str):
    at = create_access_token(user_id, email)
    rt = create_refresh_token(user_id)

    response.set_cookie(
        "access_token",
        at,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=43200,
        path="/",
    )

    response.set_cookie(
        "refresh_token",
        rt,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=604800,
        path="/",
    )


@api.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    email = body.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    ident = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": ident}, {"_id": 0})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in a few minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        cnt = (attempt.get("count", 0) if attempt else 0) + 1
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$set": {"identifier": ident, "count": cnt,
                      "locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat() if cnt >= 5 else None}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": ident})
    set_auth_cookies(response, user["id"], email)
    await log_audit(email, "LOGIN")
    return {"id": user["id"], "email": email, "name": user["name"], "role": user["role"]}


@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await log_audit(user["email"], "LOGOUT")
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}


@api.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    import jwt as _jwt
    from security import _secret, JWT_ALGORITHM
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = _jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        set_auth_cookies(response, user["id"], user["email"])
        return {"ok": True}
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
class DeptBody(BaseModel):
    name: str


@api.get("/departments")
async def list_departments(user: dict = Depends(get_current_user)):
    depts = await db.departments.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    for d in depts:
        d["recipient_count"] = await db.recipients.count_documents({"department": d["name"]})
    return depts


@api.post("/departments")
async def create_department(body: DeptBody, user: dict = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name is required")
    if await db.departments.find_one({"name": name}):
        raise HTTPException(status_code=409, detail="A department with this name already exists")
    doc = {"id": new_id(), "name": name, "created_at": now_iso()}
    await db.departments.insert_one(doc.copy())
    await log_audit(user["email"], "SETTINGS_CHANGED", doc["id"], f"Department created: {name}")
    doc.pop("_id", None)
    doc["recipient_count"] = 0
    return doc


@api.put("/departments/{dept_id}")
async def rename_department(dept_id: str, body: DeptBody, user: dict = Depends(get_current_user)):
    dept = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Department name is required")
    await db.departments.update_one({"id": dept_id}, {"$set": {"name": new_name}})
    await db.recipients.update_many({"department": dept["name"]}, {"$set": {"department": new_name}})
    await log_audit(user["email"], "SETTINGS_CHANGED", dept_id, f"Department renamed to {new_name}")
    return {"ok": True}


@api.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, user: dict = Depends(get_current_user)):
    dept = await db.departments.find_one({"id": dept_id}, {"_id": 0})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    await db.departments.delete_one({"id": dept_id})
    await db.recipients.update_many({"department": dept["name"]}, {"$set": {"department": ""}})
    await log_audit(user["email"], "SETTINGS_CHANGED", dept_id, f"Department deleted: {dept['name']}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------
class RecipientBody(BaseModel):
    email: EmailStr
    display_name: Optional[str] = ""
    department: Optional[str] = ""
    enabled: bool = True


class BulkRecipients(BaseModel):
    emails: List[str]
    department: Optional[str] = ""


def recipient_public(r: dict) -> dict:
    return {k: r[k] for k in ("id", "email", "display_name", "department", "enabled", "created_at") if k in r}


@api.get("/recipients")
async def list_recipients(
    search: Optional[str] = None, department: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    q: Dict[str, Any] = {}
    if search:
        q["email"] = {"$regex": re.escape(search), "$options": "i"}
    if department is not None and department != "":
        q["department"] = "" if department == "__none__" else department
    recs = await db.recipients.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return recs


@api.post("/recipients")
async def create_recipient(body: RecipientBody, user: dict = Depends(get_current_user)):
    email = body.email.lower().strip()
    if await db.recipients.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A recipient with this email already exists")
    doc = {
        "id": new_id(), "email": email, "display_name": (body.display_name or "").strip(),
        "department": (body.department or "").strip(), "enabled": body.enabled, "created_at": now_iso(),
    }
    await db.recipients.insert_one(doc.copy())
    await log_audit(user["email"], "RECIPIENT_CREATED", doc["id"], email)
    return recipient_public(doc)


@api.post("/recipients/bulk")
async def bulk_recipients(body: BulkRecipients, user: dict = Depends(get_current_user)):
    valid, invalid, dupes, imported = [], [], [], 0
    seen = set()
    existing = set(r["email"] for r in await db.recipients.find({}, {"email": 1, "_id": 0}).to_list(20000))
    for raw in body.emails:
        email = raw.lower().strip()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            invalid.append(raw)
            continue
        if email in existing or email in seen:
            dupes.append(email)
            continue
        seen.add(email)
        valid.append(email)
    docs = [{
        "id": new_id(), "email": e, "display_name": "",
        "department": (body.department or "").strip(), "enabled": True, "created_at": now_iso(),
    } for e in valid]
    if docs:
        await db.recipients.insert_many([d.copy() for d in docs])
        imported = len(docs)
        await log_audit(user["email"], "RECIPIENT_IMPORTED", None, f"{imported} recipients imported")
    return {"valid": len(valid), "invalid": len(invalid), "duplicates": len(dupes),
            "imported": imported, "invalid_rows": invalid, "duplicate_rows": dupes}


@api.post("/recipients/import-preview")
async def import_preview(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    content = payload.get("content", "")
    rows_valid, rows_invalid, rows_dupe = [], [], []
    seen = set()
    existing = set(r["email"] for r in await db.recipients.find({}, {"email": 1, "_id": 0}).to_list(20000))
    reader = csv.reader(io.StringIO(content))
    all_rows = list(reader)
    start = 0
    if all_rows and all_rows[0] and all_rows[0][0].strip().lower() in ("email", "e-mail"):
        start = 1
    for idx in range(start, len(all_rows)):
        row = all_rows[idx]
        if not row or not "".join(row).strip():
            continue
        email = (row[0] or "").lower().strip()
        dept = (row[1].strip() if len(row) > 1 else "")
        if not EMAIL_RE.match(email):
            rows_invalid.append({"email": row[0] if row else "", "department": dept, "reason": "Invalid email"})
        elif email in existing or email in seen:
            rows_dupe.append({"email": email, "department": dept, "reason": "Duplicate"})
        else:
            seen.add(email)
            rows_valid.append({"email": email, "department": dept})
    return {"valid": rows_valid, "invalid": rows_invalid, "duplicates": rows_dupe,
            "summary": {"valid": len(rows_valid), "invalid": len(rows_invalid), "duplicates": len(rows_dupe)}}


@api.post("/recipients/import-confirm")
async def import_confirm(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    rows = payload.get("rows", [])
    docs = []
    for r in rows:
        email = (r.get("email") or "").lower().strip()
        if not EMAIL_RE.match(email):
            continue
        if await db.recipients.find_one({"email": email}):
            continue
        docs.append({"id": new_id(), "email": email, "display_name": "",
                     "department": (r.get("department") or "").strip(), "enabled": True, "created_at": now_iso()})
    if docs:
        await db.recipients.insert_many([d.copy() for d in docs])
        await log_audit(user["email"], "RECIPIENT_IMPORTED", None, f"{len(docs)} recipients imported via CSV")
    return {"imported": len(docs)}


@api.put("/recipients/{rid}")
async def update_recipient(rid: str, body: RecipientBody, user: dict = Depends(get_current_user)):
    rec = await db.recipients.find_one({"id": rid}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")
    email = body.email.lower().strip()
    other = await db.recipients.find_one({"email": email, "id": {"$ne": rid}})
    if other:
        raise HTTPException(status_code=409, detail="Another recipient already uses this email")
    await db.recipients.update_one({"id": rid}, {"$set": {
        "email": email, "display_name": (body.display_name or "").strip(),
        "department": (body.department or "").strip(), "enabled": body.enabled,
    }})
    await log_audit(user["email"], "RECIPIENT_UPDATED", rid, email)
    return {"ok": True}

@api.delete("/activity/recipient/{srid}")
async def delete_recipient_activity(
    srid: str,
    user: dict = Depends(get_current_user)
):
    sr = await db.simulation_recipients.find_one(
        {"id": srid},
        {"_id": 0}
    )

    if not sr:
        raise HTTPException(status_code=404, detail="Simulation recipient not found")

    await db.simulation_events.delete_many({
        "recipient_id": srid
    })

    await db.form_submissions.delete_many({
        "recipient_id": srid
    })

    await db.simulation_recipients.update_one(
        {"id": srid},
        {"$set": {
            "open_count": 0,
            "first_open": None,
            "last_open": None,
            "click_count": 0,
            "first_click": None,
            "last_click": None,
            "landing_visited": False,
            "form_started": False,
            "form_submitted": False,
            "form_submitted_at": None,
            "last_activity": None
        }}
    )

    await log_audit(
        user["email"],
        "RECIPIENT_ACTIVITY_DELETED",
        srid,
        f"Activity deleted for {sr['email']}"
    )

    return {"ok": True}


@api.delete("/activity/simulation/{simulation_id}")
async def delete_simulation_activity(
    simulation_id: str,
    user: dict = Depends(get_current_user)
):
    recips = await db.simulation_recipients.find(
        {"simulation_id": simulation_id},
        {"_id": 0, "id": 1}
    ).to_list(50000)

    sr_ids = [r["id"] for r in recips]

    if sr_ids:
        await db.simulation_events.delete_many({
            "recipient_id": {"$in": sr_ids}
        })

        await db.form_submissions.delete_many({
            "recipient_id": {"$in": sr_ids}
        })

        await db.simulation_recipients.update_many(
            {"simulation_id": simulation_id},
            {"$set": {
                "open_count": 0,
                "first_open": None,
                "last_open": None,
                "click_count": 0,
                "first_click": None,
                "last_click": None,
                "landing_visited": False,
                "form_started": False,
                "form_submitted": False,
                "form_submitted_at": None,
                "last_activity": None
            }}
        )

    await log_audit(
        user["email"],
        "SIMULATION_ACTIVITY_DELETED",
        simulation_id,
        f"All activity deleted for simulation {simulation_id}"
    )

    return {"ok": True}


@api.delete("/admin/clear-all-data")
async def clear_all_data(user: dict = Depends(get_current_user)):
    collections = [
        db.simulation_events,
        db.form_submissions,
        db.simulation_recipients,
        db.simulations,
        db.recipients,
        db.senders,
        db.landing_pages,
        db.forms,
    ]

    deleted = {}

    for collection in collections:
        result = await collection.delete_many({})
        deleted[collection.name] = result.deleted_count

    await log_audit(
        user["email"],
        "ALL_OPERATIONAL_DATA_DELETED",
        "system",
        "All dashboard operational data deleted"
    )

    return {
        "ok": True,
        "message": "All operational data deleted",
        "deleted": deleted,
    }














@api.delete("/recipients/{rid}")
async def delete_recipient(rid: str, user: dict = Depends(get_current_user)):
    rec = await db.recipients.find_one({"id": rid}, {"_id": 0})

    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Find all simulation-recipient records for this recipient
    sim_recipients = await db.simulation_recipients.find(
        {"recipient_id": rid},
        {"_id": 0, "id": 1, "simulation_id": 1}
    ).to_list(10000)

    sr_ids = [x["id"] for x in sim_recipients]
    sim_ids = list({x["simulation_id"] for x in sim_recipients})

    # Delete all tracking/events/form data linked to this recipient
    if sr_ids:
        await db.simulation_events.delete_many(
            {"recipient_id": {"$in": sr_ids}}
        )

        await db.form_submissions.delete_many(
            {"recipient_id": {"$in": sr_ids}}
        )

        await db.simulation_recipients.delete_many(
            {"recipient_id": rid}
        )

    # Delete the recipient itself
    await db.recipients.delete_one({"id": rid})

    # Remove simulations that no longer have any recipients
    for sim_id in sim_ids:
        remaining = await db.simulation_recipients.count_documents(
            {"simulation_id": sim_id}
        )
        if remaining == 0:
            await db.simulations.delete_one({"id": sim_id})

    await log_audit(
        user["email"],
        "RECIPIENT_DELETED",
        rid,
        f"Recipient and all linked tracking data deleted: {rec['email']}"
    )

    return {"ok": True}


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------
class SenderBody(BaseModel):
    name: str
    email: EmailStr
    provider: str = "Resend"
    status: str = "ACTIVE"


@api.get("/senders")
async def list_senders(user: dict = Depends(get_current_user)):
    return await db.senders.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/senders")
async def create_sender(body: SenderBody, user: dict = Depends(get_current_user)):
    doc = {"id": new_id(), "name": body.name.strip(), "email": body.email.lower().strip(),
          "provider": body.provider.strip() or "Resend",
           "status": body.status if body.status in ("ACTIVE", "DISABLED") else "ACTIVE",
           "created_at": now_iso()}
    await db.senders.insert_one(doc.copy())
    await log_audit(user["email"], "SENDER_ADDED", doc["id"], doc["email"])
    doc.pop("_id", None)
    return doc


@api.put("/senders/{sid}")
async def update_sender(sid: str, body: SenderBody, user: dict = Depends(get_current_user)):
    s = await db.senders.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Sender not found")
    await db.senders.update_one({"id": sid}, {"$set": {
        "name": body.name.strip(), "email": body.email.lower().strip(),
        "provider": body.provider.strip() or "Resend",
        "status": body.status if body.status in ("ACTIVE", "DISABLED") else "ACTIVE",
    }})
    action = "SENDER_DISABLED" if body.status == "DISABLED" else "SENDER_UPDATED"
    await log_audit(user["email"], action, sid, body.email)
    return {"ok": True}


@api.delete("/senders/{sid}")
async def delete_sender(sid: str, user: dict = Depends(get_current_user)):
    await db.senders.delete_one({"id": sid})
    await log_audit(user["email"], "SENDER_UPDATED", sid, "Sender deleted")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Landing pages
# ---------------------------------------------------------------------------
class LandingBody(BaseModel):
    name: str
    title: str
    message: str = ""
    indicators: str = ""
    reporting_instructions: str = ""


@api.get("/landing-pages")
async def list_landing(user: dict = Depends(get_current_user)):
    return await db.landing_pages.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/landing-pages")
async def create_landing(body: LandingBody, user: dict = Depends(get_current_user)):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.landing_pages.insert_one(doc.copy())
    await log_audit(user["email"], "LANDING_PAGE_CREATED", doc["id"], body.name)
    doc.pop("_id", None)
    return doc


@api.put("/landing-pages/{lid}")
async def update_landing(lid: str, body: LandingBody, user: dict = Depends(get_current_user)):
    if not await db.landing_pages.find_one({"id": lid}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Landing page not found")
    await db.landing_pages.update_one({"id": lid}, {"$set": body.model_dump()})
    return {"ok": True}


@api.delete("/landing-pages/{lid}")
async def delete_landing(lid: str, user: dict = Depends(get_current_user)):
    await db.landing_pages.delete_one({"id": lid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Awareness forms
# ---------------------------------------------------------------------------
BANNED_FIELD_WORDS = ("password", "otp", "mfa", "recovery code", "auth token", "session",
                      "cookie", "credit card", "card number", "cvv", "banking", "api key", "pin")


class FormField(BaseModel):
    id: str = Field(default_factory=new_id)
    label: str
    type: str = "text"
    required: bool = False


class FormBody(BaseModel):
    name: str
    fields: List[FormField] = []


def validate_form_fields(fields: List[FormField]):
    for f in fields:
        low = f.label.lower()
        if any(w in low for w in BANNED_FIELD_WORDS):
            raise HTTPException(status_code=400,
                                detail=f"Field '{f.label}' is not allowed. Awareness forms may not collect credentials or sensitive secrets.")


@api.get("/forms")
async def list_forms(user: dict = Depends(get_current_user)):
    return await db.forms.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/forms")
async def create_form(body: FormBody, user: dict = Depends(get_current_user)):
    validate_form_fields(body.fields)
    doc = {"id": new_id(), "name": body.name.strip(),
           "fields": [f.model_dump() for f in body.fields], "created_at": now_iso()}
    await db.forms.insert_one(doc.copy())
    await log_audit(user["email"], "FORM_CREATED", doc["id"], body.name)
    doc.pop("_id", None)
    return doc


@api.put("/forms/{fid}")
async def update_form(fid: str, body: FormBody, user: dict = Depends(get_current_user)):
    validate_form_fields(body.fields)
    if not await db.forms.find_one({"id": fid}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Form not found")
    await db.forms.update_one({"id": fid}, {"$set": {"name": body.name.strip(),
                              "fields": [f.model_dump() for f in body.fields]}})
    await log_audit(user["email"], "FORM_UPDATED", fid, body.name)
    return {"ok": True}


@api.delete("/forms/{fid}")
async def delete_form(fid: str, user: dict = Depends(get_current_user)):
    await db.forms.delete_one({"id": fid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Simulations
# ---------------------------------------------------------------------------
class Tracking(BaseModel):
    open: bool = True
    click: bool = True
    landing: bool = True
    form: bool = True
    form_submit: bool = True


class SenderSim(BaseModel):
    enabled: bool = False
    from_email: Optional[str] = ""
    display_name: Optional[str] = ""


class SimulationBody(BaseModel):
    recipient_ids: List[str] = []
    recipient_emails: List[str] = []
    department: Optional[str] = None
    sender_id: Optional[str] = None
    subject: str
    body_html: str
    destination_url: Optional[str] = ""
    tracking: Tracking = Tracking()
    sender_sim: SenderSim = SenderSim()
    landing_page_id: Optional[str] = None
    form_id: Optional[str] = None
    mode: str = "sandbox"  # sandbox | live
    scheduled_at: Optional[str] = None


async def next_sim_id() -> str:
    year = datetime.now(timezone.utc).year
    count = await db.simulations.count_documents({})
    return f"SIM-{year}-{count + 1:06d}"


async def resolve_recipients(body: SimulationBody) -> List[dict]:
    recs = {}
    if body.recipient_ids:
        for r in await db.recipients.find({"id": {"$in": body.recipient_ids}}, {"_id": 0}).to_list(10000):
            recs[r["email"]] = r
    if body.department:
        dq = "" if body.department == "__none__" else body.department
        for r in await db.recipients.find({"department": dq}, {"_id": 0}).to_list(10000):
            recs[r["email"]] = r
    for raw in body.recipient_emails:
        email = raw.lower().strip()
        if not EMAIL_RE.match(email):
            continue
        if email in recs:
            continue
        existing = await db.recipients.find_one({"email": email}, {"_id": 0})
        if existing:
            recs[email] = existing
        else:
            doc = {"id": new_id(), "email": email, "display_name": "", "department": "",
                   "enabled": True, "created_at": now_iso()}
            await db.recipients.insert_one(doc.copy())
            doc.pop("_id", None)
            recs[email] = doc
    return list(recs.values())


@api.post("/simulations")
async def create_simulation(body: SimulationBody, user: dict = Depends(get_current_user)):
    if not body.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")
    if not body.body_html.strip():
        raise HTTPException(status_code=400, detail="Email body is required")
    if body.destination_url and not URL_RE.match(body.destination_url.strip()):
        raise HTTPException(status_code=400, detail="Destination URL must be a valid http/https URL")
    recipients = await resolve_recipients(body)
    if not recipients:
        raise HTTPException(status_code=400, detail="Add at least one valid recipient")

    sender = None
    if body.sender_id:
        sender = await db.senders.find_one({"id": body.sender_id}, {"_id": 0})

    sim_id = await next_sim_id()
    status = "SCHEDULED" if body.scheduled_at else "DRAFT"
    sim = {
        "id": new_id(), "sim_id": sim_id,
        "sender_id": body.sender_id, "sender_name": sender["name"] if sender else "",
        "sender_email": sender["email"] if sender else "",
        "subject": body.subject.strip(), "body_html": body.body_html,
        "destination_url": (body.destination_url or "").strip(),
        "tracking": body.tracking.model_dump(), "sender_sim": body.sender_sim.model_dump(),
        "landing_page_id": body.landing_page_id, "form_id": body.form_id,
        "mode": "live" if body.mode == "live" else "sandbox",
        "scheduled_at": body.scheduled_at, "status": status,
        "recipient_count": len(recipients), "created_by": user["email"], "created_at": now_iso(),
    }
    await db.simulations.insert_one(sim.copy())
    for r in recipients:
        await db.simulation_recipients.insert_one({
            "id": new_id(), "simulation_id": sim["id"], "recipient_id": r["id"],
            "email": r["email"], "department": r.get("department", ""),
            "token": secrets.token_urlsafe(24),
            "sent": False, "delivery_status": "PENDING",
            "open_count": 0, "first_open": None, "last_open": None,
            "click_count": 0, "first_click": None, "last_click": None,
            "landing_visited": False, "form_started": False, "form_submitted": False,
            "form_submitted_at": None, "last_activity": None,
        })
    await log_audit(user["email"], "SIMULATION_CREATED", sim["id"], sim_id)
    sim.pop("_id", None)
    return sim


@api.put("/simulations/{sid}")
async def update_simulation(sid: str, body: SimulationBody, user: dict = Depends(get_current_user)):
    sim = await db.simulations.find_one({"id": sid}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim["status"] not in ("DRAFT", "SCHEDULED"):
        raise HTTPException(status_code=400, detail="Only draft or scheduled simulations can be edited")
    if not body.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required")
    if not body.body_html.strip():
        raise HTTPException(status_code=400, detail="Email body is required")
    if body.destination_url and not URL_RE.match(body.destination_url.strip()):
        raise HTTPException(status_code=400, detail="Destination URL must be a valid http/https URL")
    recipients = await resolve_recipients(body)
    if not recipients:
        raise HTTPException(status_code=400, detail="Add at least one valid recipient")
    sender = await db.senders.find_one({"id": body.sender_id}, {"_id": 0}) if body.sender_id else None
    await db.simulations.update_one({"id": sid}, {"$set": {
        "sender_id": body.sender_id, "sender_name": sender["name"] if sender else "",
        "sender_email": sender["email"] if sender else "",
        "subject": body.subject.strip(), "body_html": body.body_html,
        "destination_url": (body.destination_url or "").strip(),
        "tracking": body.tracking.model_dump(), "sender_sim": body.sender_sim.model_dump(),
        "landing_page_id": body.landing_page_id, "form_id": body.form_id,
        "mode": "live" if body.mode == "live" else "sandbox",
        "scheduled_at": body.scheduled_at, "status": "SCHEDULED" if body.scheduled_at else "DRAFT",
        "recipient_count": len(recipients),
    }})
    await db.simulation_recipients.delete_many({"simulation_id": sid})
    for r in recipients:
        await db.simulation_recipients.insert_one({
            "id": new_id(), "simulation_id": sid, "recipient_id": r["id"],
            "email": r["email"], "department": r.get("department", ""),
            "token": secrets.token_urlsafe(24),
            "sent": False, "delivery_status": "PENDING",
            "open_count": 0, "first_open": None, "last_open": None,
            "click_count": 0, "first_click": None, "last_click": None,
            "landing_visited": False, "form_started": False, "form_submitted": False,
            "form_submitted_at": None, "last_activity": None,
        })
    updated = await db.simulations.find_one({"id": sid}, {"_id": 0})
    return updated


@api.delete("/simulations/{sid}")
async def delete_simulation(sid: str, user: dict = Depends(get_current_user)):
    sim = await db.simulations.find_one({"id": sid}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sr_ids = [
        r["id"]
        for r in await db.simulation_recipients.find(
            {"simulation_id": sid},
            {"_id": 0, "id": 1}
        ).to_list(50000)
    ]

    if sr_ids:
        await db.simulation_events.delete_many(
            {"recipient_id": {"$in": sr_ids}}
        )
        await db.form_submissions.delete_many(
            {"recipient_id": {"$in": sr_ids}}
        )

    await db.simulation_recipients.delete_many({"simulation_id": sid})
    await db.simulations.delete_one({"id": sid})

    await log_audit(
        user["email"],
        "SIMULATION_DELETED",
        sid,
        f"Simulation deleted: {sim.get('sim_id', sid)}"
    )

    return {"ok": True}




@api.get("/simulations")
async def list_simulations(user: dict = Depends(get_current_user)):
    return await db.simulations.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def sim_stats(sim_id: str) -> dict:
    q = {"simulation_id": sim_id}
    total = await db.simulation_recipients.count_documents(q)
    sent = await db.simulation_recipients.count_documents({**q, "sent": True})
    delivered = await db.simulation_recipients.count_documents({**q, "delivery_status": "DELIVERED"})
    opened = await db.simulation_recipients.count_documents({**q, "open_count": {"$gt": 0}})
    clicked = await db.simulation_recipients.count_documents({**q, "click_count": {"$gt": 0}})
    landing = await db.simulation_recipients.count_documents({**q, "landing_visited": True})
    fstart = await db.simulation_recipients.count_documents({**q, "form_started": True})
    fsub = await db.simulation_recipients.count_documents({**q, "form_submitted": True})
    return {"recipients": total, "sent": sent, "delivered": delivered, "opened": opened,
            "clicked": clicked, "landing": landing, "form_started": fstart, "form_submitted": fsub}


@api.get("/simulations/{sid}")
async def get_simulation(sid: str, user: dict = Depends(get_current_user)):
    sim = await db.simulations.find_one({"id": sid}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    sim["stats"] = await sim_stats(sid)
    return sim


@api.get("/simulations/{sid}/recipients")
async def sim_recipients(sid: str, user: dict = Depends(get_current_user)):
    return await db.simulation_recipients.find({"simulation_id": sid}, {"_id": 0}).to_list(10000)


@api.get("/simulations/{sid}/recipients/{srid}/timeline")
async def recipient_timeline(sid: str, srid: str, user: dict = Depends(get_current_user)):
    events = await db.simulation_events.find(
        {"simulation_id": sid, "recipient_id": srid}, {"_id": 0}).sort("timestamp", 1).to_list(1000)
    return events


def build_email_html(sim: dict, sr: dict) -> str:
    base = PUBLIC_BASE_URL
    click_url = f"{base}/api/track/click/{sr['token']}"
    pixel = f'<img src="{base}/api/track/open/{sr["token"]}.png" width="1" height="1" alt="" style="display:none" />' if sim["tracking"].get("open") else ""
    body = sim["body_html"]
    cta = (f'<div style="margin:24px 0"><a href="{click_url}" '
           f'style="background:#4f46e5;color:#ffffff;padding:12px 22px;border-radius:8px;'
           f'text-decoration:none;font-family:Arial,sans-serif;font-size:14px;display:inline-block">'
           f'Open Secure Document</a></div>') if sim["tracking"].get("click") else ""
    footer = (f'<p style="font-size:12px;color:#888;font-family:Arial,sans-serif;margin-top:28px">'
              f'Sent by {EMAIL_FROM_NAME}. This is an authorized internal security awareness exercise. '
              f'We never ask for your password or payment details by email.</p>')
    return (f'<table role="presentation" width="100%"><tr><td style="padding:24px;'
            f'font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#111">'
            f'{body}{cta}{footer}{pixel}</td></tr></table>')


@api.post("/simulations/{sid}/send")
async def send_simulation(sid: str, user: dict = Depends(get_current_user)):
    sim = await db.simulations.find_one({"id": sid}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    recips = await db.simulation_recipients.find({"simulation_id": sid}, {"_id": 0}).to_list(10000)
    if not recips:
        raise HTTPException(status_code=400, detail="No recipients on this simulation")

    live = sim["mode"] == "live"
    provider_error = None
    if live:
        if sim["sender_sim"].get("enabled"):
            raise HTTPException(status_code=422, detail=(
                "Simulated sender identities cannot be delivered through the authorized provider "
                "(SPF/DKIM/DMARC protections). Use Test/Sandbox mode to preview the simulated identity, "
                "or disable Sender Identity Simulation to send under the authorized sender."))
        try:
            assert_safe_email(sim["subject"], sim["body_html"])
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    sent_count = 0
    for sr in recips:
        ts = now_iso()
        html = build_email_html(sim, sr)
        if live:
            try:
                await send_email(to=sr["email"], subject=sim["subject"], html=html)
                delivery = "SENT"
            except Exception as e:
                logger.error(f"send failed for {sr['email']}: {e}")
                provider_error = "Unable to send one or more emails. Please verify the configured authorized sender."
                await db.simulation_recipients.update_one({"id": sr["id"]}, {"$set": {"delivery_status": "FAILED"}})
                continue
        else:
            delivery = "SANDBOX_SENT"
        await db.simulation_recipients.update_one({"id": sr["id"]}, {"$set": {
            "sent": True, "delivery_status": delivery, "last_activity": ts}})
        await db.simulation_events.insert_one({
            "id": new_id(), "simulation_id": sid, "recipient_id": sr["id"],
            "recipient_email": sr["email"], "event_type": "EMAIL_SENT", "timestamp": ts})
        sent_count += 1

    await db.simulations.update_one({"id": sid}, {"$set": {"status": "RUNNING"}})
    await log_audit(user["email"], "SIMULATION_LAUNCHED", sid, f"{sent_count} sent ({sim['mode']})")
    return {"sent": sent_count, "mode": sim["mode"], "provider_error": provider_error,
            "delivery_status_note": "Delivery confirmation is not provided by the provider; emails are marked SENT."}


class TestSendBody(BaseModel):
    email: EmailStr


@api.post("/simulations/{sid}/test")
async def send_test(sid: str, body: TestSendBody, user: dict = Depends(get_current_user)):
    sim = await db.simulations.find_one({"id": sid}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if sim["mode"] == "live" and sim["sender_sim"].get("enabled"):
        return {"status": "FAILED", "error": (
            "Simulated sender identity is preview/sandbox only and cannot be delivered live. "
            "Disable sender identity simulation or use Sandbox mode.")}
    if sim["mode"] != "live":
        return {"status": "SENT", "note": "Sandbox mode: test email simulated (not actually delivered)."}
    fake_sr = {"token": secrets.token_urlsafe(24)}
    html = build_email_html(sim, fake_sr)
    try:
        await send_email(to=body.email, subject=f"[TEST] {sim['subject']}", html=html)
        return {"status": "SENT"}
    except ValueError as e:
        return {"status": "FAILED", "error": str(e)}
    except Exception:
        return {"status": "FAILED", "error": "Unable to send test email. Please verify the configured authorized sender."}


class StatusBody(BaseModel):
    status: str


@api.put("/simulations/{sid}/status")
async def set_status(sid: str, body: StatusBody, user: dict = Depends(get_current_user)):
    if body.status not in SIM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.simulations.update_one({"id": sid}, {"$set": {"status": body.status}})
    action = {"PAUSED": "SIMULATION_PAUSED", "CANCELLED": "SIMULATION_CANCELLED"}.get(body.status, "SETTINGS_CHANGED")
    await log_audit(user["email"], action, sid, body.status)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sandbox simulate events
# ---------------------------------------------------------------------------
async def apply_event(sr: dict, sim_id: str, event_type: str, ts: Optional[str] = None):
    ts = ts or now_iso()
    updates: Dict[str, Any] = {"last_activity": ts}
    if event_type == "EMAIL_OPENED":
        updates["open_count"] = sr.get("open_count", 0) + 1
        updates["last_open"] = ts
        if not sr.get("first_open"):
            updates["first_open"] = ts
    elif event_type == "LINK_CLICKED":
        updates["click_count"] = sr.get("click_count", 0) + 1
        updates["last_click"] = ts
        if not sr.get("first_click"):
            updates["first_click"] = ts
    elif event_type == "LANDING_PAGE_VISITED":
        updates["landing_visited"] = True
    elif event_type == "FORM_STARTED":
        updates["form_started"] = True
    elif event_type == "FORM_SUBMITTED":
        updates["form_submitted"] = True
        updates["form_submitted_at"] = ts
    elif event_type == "EMAIL_DELIVERED":
        updates["delivery_status"] = "DELIVERED"
    elif event_type == "EMAIL_SENT":
        updates["sent"] = True
    await db.simulation_recipients.update_one({"id": sr["id"]}, {"$set": updates})
    await db.simulation_events.insert_one({
        "id": new_id(), "simulation_id": sim_id, "recipient_id": sr["id"],
        "recipient_email": sr["email"], "event_type": event_type, "timestamp": ts})


class SimEventBody(BaseModel):
    recipient_id: str
    event_type: str


@api.post("/simulations/{sid}/simulate-event")
async def simulate_event(sid: str, body: SimEventBody, user: dict = Depends(get_current_user)):
    if body.event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid event type")
    sr = await db.simulation_recipients.find_one({"id": body.recipient_id, "simulation_id": sid}, {"_id": 0})
    if not sr:
        raise HTTPException(status_code=404, detail="Recipient not found in this simulation")
    await apply_event(sr, sid, body.event_type)
    return {"ok": True}


@api.post("/simulations/{sid}/simulate-full")
async def simulate_full(sid: str, user: dict = Depends(get_current_user)):
    recips = await db.simulation_recipients.find({"simulation_id": sid}, {"_id": 0}).to_list(10000)
    import random
    seq = ["EMAIL_SENT", "EMAIL_DELIVERED", "EMAIL_OPENED", "LINK_CLICKED",
           "LANDING_PAGE_VISITED", "FORM_STARTED", "FORM_SUBMITTED"]
    for sr in recips:
        depth = random.randint(2, 7)
        cur = await db.simulation_recipients.find_one({"id": sr["id"]}, {"_id": 0})
        for ev in seq[:depth]:
            await apply_event(cur, sid, ev)
            cur = await db.simulation_recipients.find_one({"id": sr["id"]}, {"_id": 0})
    await db.simulations.update_one({"id": sid}, {"$set": {"status": "COMPLETED"}})
    return {"ok": True, "recipients": len(recips)}


# ---------------------------------------------------------------------------
# Public tracking (no auth)
# ---------------------------------------------------------------------------
@api.get("/track/open/{token}.png")
async def track_open(token: str):
    sr = await db.simulation_recipients.find_one({"token": token}, {"_id": 0})
    if sr:
        sim = await db.simulations.find_one({"id": sr["simulation_id"]}, {"_id": 0})
        if sim and sim["tracking"].get("open"):
            await apply_event(sr, sr["simulation_id"], "EMAIL_OPENED")
    return FastResponse(content=PIXEL, media_type="image/png",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@api.get("/track/click/{token}")
async def track_click(token: str):
    sr = await db.simulation_recipients.find_one({"token": token}, {"_id": 0})

    if not sr:
        return RedirectResponse(url=PUBLIC_BASE_URL or "/")

    sim = await db.simulations.find_one({"id": sr["simulation_id"]}, {"_id": 0})

    if sim and sim["tracking"].get("click"):
        await apply_event(sr, sr["simulation_id"], "LINK_CLICKED")

    if sim and sim.get("landing_page_id") and sim["tracking"].get("landing"):
        return RedirectResponse(
            url=f"{PUBLIC_BASE_URL}/lp/{token}"
        )

    dest = (sim.get("destination_url") if sim else "") or PUBLIC_BASE_URL or "/"
    return RedirectResponse(url=dest)

@api.get("/public/landing/{token}")
async def public_landing(token: str):
    sr = await db.simulation_recipients.find_one({"token": token}, {"_id": 0})
    if not sr:
        raise HTTPException(status_code=404, detail="Not found")
    sim = await db.simulations.find_one({"id": sr["simulation_id"]}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Not found")
    if sim["tracking"].get("landing"):
        cur = await db.simulation_recipients.find_one({"id": sr["id"]}, {"_id": 0})
        if not cur.get("landing_visited"):
            await apply_event(cur, sr["simulation_id"], "LANDING_PAGE_VISITED")
    lp = await db.landing_pages.find_one({"id": sim.get("landing_page_id")}, {"_id": 0}) if sim.get("landing_page_id") else None
    form = await db.forms.find_one({"id": sim.get("form_id")}, {"_id": 0}) if sim.get("form_id") else None
    return {"landing_page": lp, "form": form if sim["tracking"].get("form") else None,
            "form_enabled": bool(form and sim["tracking"].get("form"))}


@api.post("/public/form-start/{token}")
async def public_form_start(token: str):
    sr = await db.simulation_recipients.find_one({"token": token}, {"_id": 0})
    if not sr:
        raise HTTPException(status_code=404, detail="Not found")
    sim = await db.simulations.find_one({"id": sr["simulation_id"]}, {"_id": 0})
    if sim and sim["tracking"].get("form") and not sr.get("form_started"):
        await apply_event(sr, sr["simulation_id"], "FORM_STARTED")
    return {"ok": True}


@api.post("/public/form-submit/{token}")
async def public_form_submit(token: str, request: Request):
    sr = await db.simulation_recipients.find_one({"token": token}, {"_id": 0})
    if not sr:
        raise HTTPException(status_code=404, detail="Not found")
    sim = await db.simulations.find_one({"id": sr["simulation_id"]}, {"_id": 0})
    if not sim:
        raise HTTPException(status_code=404, detail="Not found")
    payload = await request.json()
    responses = payload.get("responses", {})
    # Never store credentials even if injected
    safe = {k: v for k, v in responses.items() if not any(w in str(k).lower() for w in BANNED_FIELD_WORDS)}
    if sim["tracking"].get("form_submit"):
        cur = await db.simulation_recipients.find_one({"id": sr["id"]}, {"_id": 0})
        await apply_event(cur, sr["simulation_id"], "FORM_SUBMITTED")
        await db.form_submissions.insert_one({
            "id": new_id(), "simulation_id": sr["simulation_id"], "recipient_id": sr["id"],
            "form_id": sim.get("form_id"), "responses": safe, "timestamp": now_iso()})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Analytics / Dashboard
# ---------------------------------------------------------------------------
@api.get("/analytics/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    total_sims = await db.simulations.count_documents({})
    total_recips = await db.recipients.count_documents({})
    sr = db.simulation_recipients
    sent = await sr.count_documents({"sent": True})
    delivered = await sr.count_documents({"delivery_status": "DELIVERED"})
    opened = await sr.count_documents({"open_count": {"$gt": 0}})
    clicked = await sr.count_documents({"click_count": {"$gt": 0}})
    landing = await sr.count_documents({"landing_visited": True})
    fstart = await sr.count_documents({"form_started": True})
    fsub = await sr.count_documents({"form_submitted": True})

    def rate(n, d):
        return round(100 * n / d, 1) if d else 0.0

    # activity over time (last 14 days) from events
    events = await db.simulation_events.find({}, {"_id": 0}).to_list(50000)
    by_day: Dict[str, Dict[str, int]] = {}
    for e in events:
        day = e["timestamp"][:10]
        by_day.setdefault(day, {"opens": 0, "clicks": 0, "sent": 0, "submits": 0})
        if e["event_type"] == "EMAIL_OPENED":
            by_day[day]["opens"] += 1
        elif e["event_type"] == "LINK_CLICKED":
            by_day[day]["clicks"] += 1
        elif e["event_type"] == "EMAIL_SENT":
            by_day[day]["sent"] += 1
        elif e["event_type"] == "FORM_SUBMITTED":
            by_day[day]["submits"] += 1
    activity = [{"date": d, **v} for d, v in sorted(by_day.items())][-14:]

    recent_events = await db.simulation_events.find({}, {"_id": 0}).sort("timestamp", -1).to_list(15)
    recent_sims = await db.simulations.find({}, {"_id": 0}).sort("created_at", -1).to_list(6)
    for s in recent_sims:
        s["stats"] = await sim_stats(s["id"])

    return {
        "cards": {"total_simulations": total_sims, "total_recipients": total_recips,
                  "emails_sent": sent, "emails_delivered": delivered, "observed_opens": opened,
                  "link_clicks": clicked, "landing_page_visits": landing,
                  "forms_started": fstart, "forms_submitted": fsub},
        "rates": {"open_rate": rate(opened, sent), "click_rate": rate(clicked, sent),
                  "landing_rate": rate(landing, sent), "form_start_rate": rate(fstart, sent),
                  "form_submission_rate": rate(fsub, sent)},
        "activity": activity,
        "opens_vs_clicks": {"opens": opened, "clicks": clicked, "submits": fsub},
        "recent_events": recent_events, "recent_simulations": recent_sims,
    }


@api.get("/analytics/departments")
async def dept_analytics(user: dict = Depends(get_current_user)):
    depts = await db.departments.find({}, {"_id": 0}).to_list(1000)
    names = [d["name"] for d in depts] + ["__none__"]
    result = []
    for name in names:
        q = {"department": "" if name == "__none__" else name}
        recips = await db.simulation_recipients.find(q, {"_id": 0}).to_list(20000)
        rcount = await db.recipients.count_documents(q)
        sent = sum(1 for r in recips if r.get("sent"))
        delivered = sum(1 for r in recips if r.get("delivery_status") == "DELIVERED")
        opened = sum(1 for r in recips if r.get("open_count", 0) > 0)
        clicked = sum(1 for r in recips if r.get("click_count", 0) > 0)
        fstart = sum(1 for r in recips if r.get("form_started"))
        fsub = sum(1 for r in recips if r.get("form_submitted"))
        result.append({"department": "No Department" if name == "__none__" else name,
                       "recipients": rcount, "sent": sent, "delivered": delivered,
                       "opened": opened, "clicked": clicked, "form_started": fstart,
                       "form_submitted": fsub,
                       "click_rate": round(100 * clicked / sent, 1) if sent else 0.0})
    return result


@api.get("/analytics/recipients")
async def recipient_analytics(
    simulation_id: Optional[str] = None, search: Optional[str] = None,
    filter: Optional[str] = None, department: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    q: Dict[str, Any] = {}
    if simulation_id:
        q["simulation_id"] = simulation_id
    if search:
        q["email"] = {"$regex": re.escape(search), "$options": "i"}
    if department:
        q["department"] = "" if department == "__none__" else department
    if filter == "opened":
        q["open_count"] = {"$gt": 0}
    elif filter == "not_opened":
        q["open_count"] = 0
    elif filter == "clicked":
        q["click_count"] = {"$gt": 0}
    elif filter == "not_clicked":
        q["click_count"] = 0
    elif filter == "form_started":
        q["form_started"] = True
    elif filter == "form_submitted":
        q["form_submitted"] = True
    return await db.simulation_recipients.find(q, {"_id": 0}).sort("last_activity", -1).to_list(20000)


# ---------------------------------------------------------------------------
# Reports (CSV export)
# ---------------------------------------------------------------------------
def csv_response(rows: List[dict], fieldnames: List[str], filename: str):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@api.get("/reports/recipient")
async def report_recipient(
    simulation_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    q = {"simulation_id": simulation_id} if simulation_id else {}

    recips = await db.simulation_recipients.find(
        q, {"_id": 0}
    ).to_list(50000)

    sims = {
        s["id"]: s
        for s in await db.simulations.find({}, {"_id": 0}).to_list(5000)
    }

    rows = []
    dynamic_fields = set()

    for r in recips:
        s = sims.get(r["simulation_id"], {})

        submission = await db.form_submissions.find_one(
            {
                "simulation_id": r["simulation_id"],
                "recipient_id": r["id"]
            },
            {"_id": 0},
            sort=[("timestamp", -1)]
        )

        responses = submission.get("responses", {}) if submission else {}

        for key in responses.keys():
            dynamic_fields.add(str(key))

        row = {
            "simulation_id": s.get("sim_id", ""),
            "recipient_email": r.get("email", ""),
            "department": r.get("department", ""),
            "sent": r.get("sent"),
            "delivered": r.get("delivery_status"),
            "first_open": r.get("first_open"),
            "last_open": r.get("last_open"),
            "open_count": r.get("open_count"),
            "first_click": r.get("first_click"),
            "last_click": r.get("last_click"),
            "click_count": r.get("click_count"),
            "landing_page_visited": r.get("landing_visited"),
            "form_started": r.get("form_started"),
            "form_submitted": r.get("form_submitted"),
            "submission_time": r.get("form_submitted_at"),
            "last_activity": r.get("last_activity"),
            **responses,
        }

        rows.append(row)

    base_columns = [
        "simulation_id",
        "recipient_email",
        "department",
        "sent",
        "delivered",
        "first_open",
        "last_open",
        "open_count",
        "first_click",
        "last_click",
        "click_count",
        "landing_page_visited",
        "form_started",
        "form_submitted",
        "submission_time",
        "last_activity",
    ]

    columns = base_columns + sorted(dynamic_fields)

    await log_audit(
        user["email"],
        "REPORT_EXPORTED",
        None,
        "Recipient report"
    )

    return csv_response(
        rows,
        columns,
        "recipient_report.csv"
    )


@api.get("/reports/department")
async def report_department(user: dict = Depends(get_current_user)):
    data = await dept_analytics(user)
    await log_audit(user["email"], "REPORT_EXPORTED", None, "Department report")
    return csv_response(data, list(data[0].keys()) if data else
                        ["department", "recipients", "sent", "delivered", "opened", "clicked",
                         "form_started", "form_submitted", "click_rate"], "department_report.csv")


@api.get("/reports/event")
async def report_event(simulation_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"simulation_id": simulation_id} if simulation_id else {}
    events = await db.simulation_events.find(q, {"_id": 0}).sort("timestamp", 1).to_list(100000)
    await log_audit(user["email"], "REPORT_EXPORTED", None, "Event report")
    return csv_response(events, ["timestamp", "event_type", "recipient_email", "simulation_id", "recipient_id"],
                        "event_report.csv")


@api.get("/reports/simulation-summary")
async def report_simulation_summary(user: dict = Depends(get_current_user)):
    sims = await db.simulations.find({}, {"_id": 0}).to_list(5000)
    rows = []
    for s in sims:
        st = await sim_stats(s["id"])
        rows.append({"simulation_id": s["sim_id"], "created_at": s["created_at"],
                     "sender": s.get("sender_email", ""), "subject": s["subject"],
                     "status": s["status"], **st})
    await log_audit(user["email"], "REPORT_EXPORTED", None, "Simulation summary")
    return csv_response(rows, list(rows[0].keys()) if rows else
                        ["simulation_id", "created_at", "sender", "subject", "status"],
                        "simulation_summary.csv")


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------
@api.get("/audit-logs")
async def audit_logs(action: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"action": action} if action else {}
    return await db.audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).to_list(2000)


# ---------------------------------------------------------------------------
# Settings + retention
# ---------------------------------------------------------------------------
class SettingsBody(BaseModel):
    retention_days: int = 90
    default_mode: str = "sandbox"


@api.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    s = await db.settings.find_one({"id": "global"}, {"_id": 0})
    if not s:
        s = {"id": "global", "retention_days": 90, "default_mode": "sandbox"}
        await db.settings.insert_one(s.copy())
    return s


@api.put("/settings")
async def update_settings(body: SettingsBody, user: dict = Depends(get_current_user)):
    if body.retention_days not in (30, 90, 180, 365):
        raise HTTPException(status_code=400, detail="Retention must be 30, 90, 180 or 365 days")
    await db.settings.update_one({"id": "global"},
                                 {"$set": {"retention_days": body.retention_days, "default_mode": body.default_mode}},
                                 upsert=True)
    await log_audit(user["email"], "SETTINGS_CHANGED", None, f"retention={body.retention_days}")
    return {"ok": True}


@api.get("/settings/expired-simulations")
async def expired_sims(user: dict = Depends(get_current_user)):
    s = await db.settings.find_one({"id": "global"}, {"_id": 0})
    days = (s or {}).get("retention_days", 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sims = await db.simulations.find({"created_at": {"$lt": cutoff}}, {"_id": 0}).to_list(5000)
    return {"cutoff": cutoff, "retention_days": days, "count": len(sims), "simulations": sims}


@api.delete("/settings/expired-simulations")
async def delete_expired(user: dict = Depends(get_current_user)):
    s = await db.settings.find_one({"id": "global"}, {"_id": 0})
    days = (s or {}).get("retention_days", 90)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sims = await db.simulations.find({"created_at": {"$lt": cutoff}}, {"_id": 0}).to_list(5000)
    ids = [x["id"] for x in sims]
    if ids:
        await db.simulation_recipients.delete_many({"simulation_id": {"$in": ids}})
        await db.simulation_events.delete_many({"simulation_id": {"$in": ids}})
        await db.form_submissions.delete_many({"simulation_id": {"$in": ids}})
        await db.simulations.delete_many({"id": {"$in": ids}})
    await log_audit(user["email"], "SETTINGS_CHANGED", None, f"Deleted {len(ids)} expired simulations")
    return {"deleted": len(ids)}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.recipients.create_index("email", unique=True)
    await db.simulation_recipients.create_index("token", unique=True)
    await db.login_attempts.create_index("identifier")

    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_pw = os.environ["ADMIN_PASSWORD"]
    # Always reset the admin to a known-good password and clear any lockout so credentials are deterministic.
    await db.login_attempts.delete_many({})
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({"id": new_id(), "email": admin_email,
                                   "password_hash": hash_password(admin_pw),
                                   "name": "Security Ops Lead", "role": "admin",
                                   "created_at": now_iso()})
        logger.info("Seeded admin user")
    else:
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_pw), "role": "admin"}})

    if not await db.settings.find_one({"id": "global"}):
        await db.settings.insert_one({"id": "global", "retention_days": 90, "default_mode": "sandbox"})

    # Seed one editable authorized sender + a landing page + a form (all editable via UI)
    if await db.senders.count_documents({}) == 0:
        await db.senders.insert_one({"id": new_id(), "name": "Talbros Security",
                                     "email": "security-awareness@talbros.test",
                                     "provider": "Resend", "status": "ACTIVE",
                                     "created_at": now_iso()})
    if await db.landing_pages.count_documents({}) == 0:
        await db.landing_pages.insert_one({
            "id": new_id(), "name": "Talbros Security Awareness Check",
            "title": "TALBROS SECURITY AWARENESS CHECK",
            "message": "This was a simulated phishing awareness exercise conducted by the Talbros Security team. No harm was done.",
            "indicators": "Check the sender address carefully. Hover links before clicking. Be wary of urgency and unexpected requests.",
            "reporting_instructions": "If you receive a suspicious email, report it to security@talbros.test using the Report Phish button.",
            "created_at": now_iso()})
    if await db.forms.count_documents({}) == 0:
        await db.forms.insert_one({
            "id": new_id(), "name": "Awareness Acknowledgement",
            "fields": [
                {"id": new_id(), "label": "Full Name", "type": "text", "required": True},
                {"id": new_id(), "label": "Department", "type": "text", "required": False},
                {"id": new_id(), "label": "What made this email look suspicious?", "type": "textarea", "required": False},
            ], "created_at": now_iso()})


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": APP_NAME}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
