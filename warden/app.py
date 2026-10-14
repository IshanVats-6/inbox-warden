"""Web app: connect mailboxes, review the taxonomy and runs, change settings. Also hosts the scheduler."""

import contextlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from croniter import croniter
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import agent, db, taxonomy
from .config import settings
from .gmail import SCOPES, backend, encrypt

HERE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))


# ---------- scheduler ----------

def next_run():
    tz = ZoneInfo(settings.timezone)
    return croniter(settings.schedule, datetime.now(tz)).get_next(datetime)


def scheduler_loop(stop):
    while not stop.is_set():
        wait = (next_run() - datetime.now(ZoneInfo(settings.timezone))).total_seconds()
        if stop.wait(max(1, wait)):
            return
        agent.run("schedule")


def seed_demo():
    from .demo import COMPANY, MAILBOXES
    if db.rows("SELECT 1 FROM mailboxes"):
        return
    for email in MAILBOXES:
        db.execute("INSERT INTO mailboxes(email, auth, added_at) VALUES(?, 'demo', ?)", email, db.now())
    db.put("company", COMPANY)
    db.put("dry_run", False)
    agent.run("schedule")


@contextlib.asynccontextmanager
async def lifespan(_app):
    db.init()
    taxonomy.seed()
    if settings.demo_mode:
        seed_demo()
    stop = threading.Event()
    threading.Thread(target=scheduler_loop, args=(stop,), daemon=True).start()
    yield
    stop.set()


if not settings.secret_key and not settings.demo_mode:
    raise SystemExit("Set SECRET_KEY (any long random string). See .env.example.")
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key or "demo-only", same_site="lax",
                   https_only=settings.public_url.startswith("https"))
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


def authed(request):
    return settings.demo_mode or request.session.get("ok") is True


def page(request, name, **ctx):
    if not authed(request):
        return RedirectResponse("/login", status_code=303)
    company = db.get("company", agent.default_company())
    return templates.TemplateResponse(request, name, {"active": name.split(".")[0], "company": company, "mailbox": "",
                                                      "side_boxes": side_boxes(), "dry_run": agent.is_dry_run(),
                                                      "demo": settings.demo_mode, **ctx})


def side_boxes():
    """Sidebar mailbox list: grouped by domain, folded once there are more than four."""
    boxes = db.rows("SELECT email, mode FROM mailboxes ORDER BY email")
    domains = {}
    for b in boxes:
        domains.setdefault(b["email"].split("@", 1)[1], []).append(b)
    return {"total": len(boxes), "folded": len(boxes) > 4, "domains": sorted(domains.items())}


def fmt_time(ts):
    return datetime.fromtimestamp(ts, ZoneInfo(settings.timezone)).strftime("%d %b, %H:%M") if ts else ""


PALETTE = ["#2f54e0", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#64748b"]


def dot(path):
    top = path.split("/")[0]
    return PALETTE[sum(map(ord, top)) % len(PALETTE)]


templates.env.filters["when"] = fmt_time
templates.env.filters["dot"] = dot
templates.env.tests["search"] = lambda value, needle: needle in value


# ---------- auth ----------

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if settings.admin_password and hmac.compare_digest(password.encode(), settings.admin_password.encode()):
        request.session["ok"] = True
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- pages ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    runs = db.rows("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    last = runs[0] if runs else None
    totals = db.rows("SELECT COUNT(*) n, SUM(action IN ('archive','archive_unread')) archived, "
                     "SUM(action='attention') attention FROM decisions d JOIN runs r ON r.id=d.run_id WHERE r.dry_run=0")[0]
    attention = db.rows("SELECT * FROM decisions WHERE action='attention' ORDER BY at DESC LIMIT 6")
    recent = db.rows("SELECT * FROM decisions ORDER BY at DESC LIMIT 8")
    return page(request, "dashboard.html", last=last, last_stats=json.loads(last["stats"]) if last else {},
                totals=totals, attention=attention, recent=recent,
                mailboxes=db.rows("SELECT COUNT(*) n FROM mailboxes")[0]["n"],
                labels=db.rows("SELECT COUNT(*) n, SUM(origin='agent') agent FROM labels")[0],
                next_run=next_run().strftime("%a %d %b, %H:%M"), link=backend().link)


@app.get("/mailboxes", response_class=HTMLResponse)
def mailboxes(request: Request, error: str = ""):
    boxes = db.rows("SELECT * FROM mailboxes ORDER BY email")
    for b in boxes:
        try:
            b["total"] = backend().profile(b["email"]).get("messagesTotal")
            b["ok"] = True
        except Exception as ex:
            b["ok"], b["error"] = False, str(ex)[:120]
    return page(request, "mailboxes.html", boxes=boxes, error=error, can_oauth=bool(settings.google_client_id))


@app.post("/mailboxes/{email}")
def update_mailbox(request: Request, email: str, mode: str = Form(...), min_age_hours: int = Form(0)):
    if authed(request) and mode in ("clean", "label_only", "paused"):
        db.execute("UPDATE mailboxes SET mode=?, min_age_hours=? WHERE email=?", mode, max(0, min_age_hours), email)
    return RedirectResponse("/mailboxes", status_code=303)


@app.post("/mailboxes/{email}/remove")
def remove_mailbox(request: Request, email: str):
    if authed(request):
        db.execute("DELETE FROM mailboxes WHERE email=?", email)
    return RedirectResponse("/mailboxes", status_code=303)


@app.get("/labels", response_class=HTMLResponse)
def labels(request: Request):
    groups = {}
    for l in taxonomy.all_labels():
        groups.setdefault(l["path"].split("/")[0], []).append(l)
    return page(request, "labels.html", groups=groups)


@app.post("/labels/{path:path}/disposition")
def set_disposition(request: Request, path: str, disposition: str = Form(...)):
    if authed(request) and disposition in taxonomy.DISPOSITIONS:
        db.execute("UPDATE labels SET disposition=? WHERE path=?", disposition, path)
    return RedirectResponse("/labels", status_code=303)


@app.post("/labels-new")
def new_label(request: Request, path: str = Form(...), description: str = Form(""), disposition: str = Form("archive")):
    path = taxonomy.clean_path(path)
    if authed(request) and path:
        taxonomy.add(path, description, disposition, origin="user")
    return RedirectResponse("/labels", status_code=303)


@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request, run: int = 0, mailbox: str = ""):
    runs = db.rows("SELECT * FROM runs ORDER BY started_at DESC LIMIT 30")
    for r in runs:
        r["stats"] = json.loads(r["stats"])
    selected = run or (runs[0]["id"] if runs else 0)
    where, args = "run_id=?", [selected]
    if mailbox:
        where, args = where + " AND mailbox=?", args + [mailbox]
    shown = db.rows(f"SELECT COUNT(*) n FROM decisions WHERE {where}", *args)[0]["n"]
    decisions = db.rows(f"SELECT * FROM decisions WHERE {where} "
                        "ORDER BY attention DESC, action='keep' DESC, label LIMIT 300", *args)
    return page(request, "activity.html", runs=runs, selected=selected, decisions=decisions, shown=shown,
                mailbox=mailbox, link=backend().link)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, saved: int = 0):
    return page(request, "settings.html", saved=saved, s=settings, next_run=next_run().strftime("%a %d %b, %H:%M"))


@app.post("/settings")
def save_settings(request: Request, name: str = Form(""), description: str = Form(""), live: str = Form("")):
    if authed(request):
        db.put("company", {"name": name.strip()[:120], "description": description.strip()[:2000]})
        db.put("dry_run", live != "on")
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/run")
def run_now(request: Request, preview: str = Form("")):
    if authed(request):
        threading.Thread(target=agent.run, args=("manual", True if preview else None), daemon=True).start()
        time.sleep(1.5)
    return RedirectResponse("/activity", status_code=303)


@app.get("/health")
def health():
    return {"ok": True}


# ---------- Google sign-in to connect a mailbox ----------

@app.get("/connect/google")
def connect_google(request: Request):
    if not authed(request):
        return RedirectResponse("/login", status_code=303)
    request.session["oauth_state"] = state = secrets.token_urlsafe(24)
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": f"{settings.public_url}/oauth/callback",
        "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline",
        "prompt": "consent select_account", "state": state}))


@app.get("/oauth/callback")
def oauth_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    expected = request.session.pop("oauth_state", "")
    if not authed(request) or not expected or not hmac.compare_digest(state, expected):
        return RedirectResponse("/mailboxes?error=Sign-in+expired,+try+again", status_code=303)
    if error or not code:
        return RedirectResponse(f"/mailboxes?{urlencode({'error': error or 'Google sign-in was cancelled'})}", status_code=303)
    tok = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": f"{settings.public_url}/oauth/callback", "grant_type": "authorization_code"}).json()
    if "refresh_token" not in tok:
        return RedirectResponse("/mailboxes?error=Google+returned+no+refresh+token", status_code=303)
    who = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", timeout=30,
                       headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    db.execute("INSERT OR REPLACE INTO mailboxes(email, auth, refresh_token, added_at) VALUES(?, 'oauth', ?, ?)",
               who["emailAddress"].lower(), encrypt(tok["refresh_token"]), db.now())
    return RedirectResponse("/mailboxes", status_code=303)
