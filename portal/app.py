"""Taxcart client portal: sign-in, client setup for staff, and the sales and tax report."""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.errors import UniqueViolation

from . import config, db, engine, security

logger = logging.getLogger("portal")
COOKIE = "tc_session"
PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_REPORT_DAYS = 400

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def create_app(settings=None, fetch_summary=engine.fetch_summary):
    settings = settings or config.load()
    db.migrate(settings.database_url)
    _bootstrap_admin(settings)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def connect():
        return db.connect(settings.database_url)

    def audit(conn, actor, action, **detail):
        conn.execute("INSERT INTO audit_log (actor_user_id, action, detail) VALUES (%s, %s, %s)",
                     (actor, action, json.dumps(detail)))

    # ------------------------------------------------------------ plumbing
    @app.exception_handler(ApiError)
    async def api_error(_request, exc):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse({"error": {"code": "bad_request", "message": "Some of the details sent were not valid."}}, status_code=400)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        is_api = request.url.path.startswith("/api/")
        if is_api and request.method not in ("GET", "HEAD", "OPTIONS"):
            # Changes must come from our own pages: a custom header a foreign form
            # cannot send, and an Origin that matches when the browser supplies one.
            origin = request.headers.get("origin")
            if request.headers.get("x-requested-with") != "taxcart" or (origin and origin.rstrip("/") not in settings.origins):
                return JSONResponse({"error": {"code": "forbidden", "message": "Request not allowed."}}, status_code=403)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error on %s", request.url.path)
            response = JSONResponse({"error": {"code": "server_error", "message": "Something went wrong. Please try again."}}, status_code=500)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        return response

    def client_ip(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or (request.client.host if request.client else "")

    async def body(request):
        try:
            data = await request.json()
        except Exception:
            data = None
        if not isinstance(data, dict):
            raise ApiError(400, "bad_request", "The request could not be read.")
        return data

    def set_cookie(response, token):
        response.set_cookie(COOKIE, token, max_age=settings.session_days * 86400, httponly=True,
                            secure=settings.cookie_secure, samesite="lax", path="/")

    # ------------------------------------------------------------ who is asking
    def current_user(request: Request, allow_pending_password=False):
        token = request.cookies.get(COOKIE)
        if not token:
            raise ApiError(401, "signed_out", "Please sign in.")
        with connect() as conn:
            user = conn.execute(
                """SELECT u.id, u.email, u.is_staff, u.must_change_password
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.token_hash = %s AND s.expires_at > now() AND NOT u.disabled""",
                (security.token_hash(token),)).fetchone()
        if not user:
            raise ApiError(401, "signed_out", "Your session has ended. Please sign in again.")
        if user["must_change_password"] and not allow_pending_password:
            raise ApiError(403, "password_change_required", "Choose a new password to continue.")
        return user

    def user_or_pending(request: Request):
        return current_user(request, allow_pending_password=True)

    def staff_user(request: Request):
        user = current_user(request)
        if not user["is_staff"]:
            raise ApiError(403, "forbidden", "You do not have access to that.")
        return user

    def tenant_for(conn, user, tenant_id):
        """The tenant row if this person may see it. Same answer for 'missing' and 'not yours'."""
        row = None
        if UUID_RE.fullmatch(str(tenant_id)):
            row = conn.execute(
                """SELECT t.id, t.name FROM tenants t
                   WHERE t.id = %(t)s AND (%(staff)s OR EXISTS (
                     SELECT 1 FROM tenant_members m WHERE m.tenant_id = t.id AND m.user_id = %(u)s))""",
                {"t": tenant_id, "u": user["id"], "staff": user["is_staff"]}).fetchone()
        if not row:
            raise ApiError(404, "not_found", "We could not find that company.")
        return row

    # ------------------------------------------------------------ sign-in
    @app.post("/api/auth/login")
    async def login(request: Request):
        data = await body(request)
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password")
        if not email or not isinstance(password, str) or not password:
            raise ApiError(400, "bad_request", "Enter your email and password.")
        ip = client_ip(request)
        with connect() as conn:
            if security.is_throttled(conn, email, ip):
                raise ApiError(429, "too_many_attempts", "Too many attempts. Please wait a few minutes and try again.")
            user = conn.execute("SELECT id, password_hash, disabled, must_change_password FROM users WHERE email = %s",
                                (email,)).fetchone()
            if user:
                ok = security.verify_password(password[:security.MAX_PASSWORD], user["password_hash"]) and not user["disabled"]
            else:
                security.burn_time(password[:security.MAX_PASSWORD])
                ok = False
            security.record_attempt(conn, email, ip, ok)
            if not ok:
                audit(conn, None, "login.failed", email_key=security.email_key(email))
                conn.commit()
                # One message for every failure, so it never reveals which addresses have accounts.
                raise ApiError(401, "invalid_login", "Email or password is incorrect.")
            token = security.new_session_token()
            conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                         (security.token_hash(token), user["id"],
                          datetime.now(timezone.utc) + timedelta(days=settings.session_days)))
            conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
            conn.execute("DELETE FROM sessions WHERE expires_at < now()")
            audit(conn, user["id"], "login.ok")
        response = JSONResponse({"ok": True, "must_change_password": user["must_change_password"]})
        set_cookie(response, token)
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        token = request.cookies.get(COOKIE)
        if token:
            with connect() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash = %s", (security.token_hash(token),))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.post("/api/auth/change-password")
    async def change_password(request: Request, user=Depends(user_or_pending)):
        data = await body(request)
        current, new = data.get("current_password"), data.get("new_password")
        problem = security.password_problem(new, user["email"])
        if problem:
            raise ApiError(400, "weak_password", problem)
        with connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE id = %s", (user["id"],)).fetchone()
            if not isinstance(current, str) or not security.verify_password(current, row["password_hash"]):
                raise ApiError(400, "wrong_password", "Your current password is incorrect.")
            if current == new:
                raise ApiError(400, "weak_password", "Choose a password you have not used here before.")
            conn.execute("UPDATE users SET password_hash = %s, must_change_password = false WHERE id = %s",
                         (security.hash_password(new), user["id"]))
            # Every other device is signed out; this one gets a fresh session.
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user["id"],))
            token = security.new_session_token()
            conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                         (security.token_hash(token), user["id"],
                          datetime.now(timezone.utc) + timedelta(days=settings.session_days)))
            audit(conn, user["id"], "password.changed")
        response = JSONResponse({"ok": True})
        set_cookie(response, token)
        return response

    @app.get("/api/session")
    def session(user=Depends(user_or_pending)):
        tenants = []
        if not user["must_change_password"]:
            with connect() as conn:
                tenants = conn.execute(
                    """SELECT t.id::text AS id, t.name,
                              EXISTS (SELECT 1 FROM tenant_sources s WHERE s.tenant_id = t.id) AS has_data_source,
                              (SELECT count(*) FROM tenant_countries c WHERE c.tenant_id = t.id) AS countries
                       FROM tenants t
                       WHERE %(staff)s OR EXISTS (
                         SELECT 1 FROM tenant_members m WHERE m.tenant_id = t.id AND m.user_id = %(u)s)
                       ORDER BY lower(t.name)""",
                    {"u": user["id"], "staff": user["is_staff"]}).fetchall()
        return {"user": {"email": user["email"], "is_staff": user["is_staff"],
                         "must_change_password": user["must_change_password"]},
                "tenants": tenants}

    # ------------------------------------------------------------ report
    @app.get("/api/reports/sales-tax")
    def sales_tax(tenant: str, date_from: date, date_to: date, user=Depends(current_user)):
        if date_to < date_from:
            raise ApiError(400, "bad_request", "The end date is before the start date.")
        if (date_to - date_from).days > MAX_REPORT_DAYS:
            raise ApiError(400, "bad_request", "Choose a period of 13 months or less.")
        with connect() as conn:
            row = tenant_for(conn, user, tenant)
            source = conn.execute("SELECT ref FROM tenant_sources WHERE tenant_id = %s AND kind = 'shopify'",
                                  (row["id"],)).fetchone()
            configured = conn.execute(
                "SELECT country, split_by_region FROM tenant_countries WHERE tenant_id = %s "
                "ORDER BY (country <> 'US'), country", (row["id"],)).fetchall()
        base = {"tenant": {"id": str(row["id"]), "name": row["name"]}}
        if not source or not configured:
            # Not an error: the page explains that setup is not finished.
            return {**base, "status": "not_set_up",
                    "missing": [m for m, absent in (("data_source", not source), ("countries", not configured)) if absent]}
        try:
            summary = fetch_summary(settings, source["ref"], date_from, date_to,
                                    [c["country"] for c in configured],
                                    [c["country"] for c in configured if c["split_by_region"]])
        except engine.EngineError as e:
            raise ApiError(e.status, "report_unavailable", str(e))
        return {**base, "status": "ready", **engine.shape(summary, configured, user["is_staff"])}

    # ------------------------------------------------------------ staff: clients
    def tenant_detail(conn, tenant_id):
        t = conn.execute("SELECT id::text AS id, name FROM tenants WHERE id = %s", (tenant_id,)).fetchone()
        if not t:
            raise ApiError(404, "not_found", "We could not find that company.")
        source = conn.execute("SELECT ref FROM tenant_sources WHERE tenant_id = %s AND kind = 'shopify'", (tenant_id,)).fetchone()
        t["shop_domain"] = source["ref"] if source else None
        t["countries"] = conn.execute(
            "SELECT country, split_by_region FROM tenant_countries WHERE tenant_id = %s ORDER BY (country <> 'US'), country",
            (tenant_id,)).fetchall()
        t["users"] = conn.execute(
            """SELECT u.id::text AS id, u.email, u.disabled, u.must_change_password, u.last_login_at
               FROM tenant_members m JOIN users u ON u.id = m.user_id
               WHERE m.tenant_id = %s ORDER BY u.email""", (tenant_id,)).fetchall()
        return t

    def valid_uuid(value):
        if not UUID_RE.fullmatch(str(value)):
            raise ApiError(404, "not_found", "We could not find that.")
        return str(value)

    @app.get("/api/admin/tenants")
    def admin_tenants(_user=Depends(staff_user)):
        with connect() as conn:
            ids = conn.execute("SELECT id FROM tenants ORDER BY lower(name)").fetchall()
            return {"tenants": [tenant_detail(conn, r["id"]) for r in ids]}

    @app.post("/api/admin/tenants")
    async def admin_create_tenant(request: Request, user=Depends(staff_user)):
        name = str((await body(request)).get("name", "")).strip()
        if not 1 <= len(name) <= 120:
            raise ApiError(400, "bad_request", "Enter the company name.")
        with connect() as conn:
            tenant_id = conn.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,)).fetchone()["id"]
            audit(conn, user["id"], "tenant.created", tenant=str(tenant_id), name=name)
            return {"tenant": tenant_detail(conn, tenant_id)}

    @app.put("/api/admin/tenants/{tenant_id}")
    async def admin_update_tenant(tenant_id: str, request: Request, user=Depends(staff_user)):
        tenant_id = valid_uuid(tenant_id)
        data = await body(request)
        with connect() as conn:
            tenant_detail(conn, tenant_id)  # 404 if missing
            if "name" in data:
                name = str(data["name"]).strip()
                if not 1 <= len(name) <= 120:
                    raise ApiError(400, "bad_request", "Enter the company name.")
                conn.execute("UPDATE tenants SET name = %s WHERE id = %s", (name, tenant_id))
            if "shop_domain" in data:
                shop = str(data["shop_domain"] or "").strip().lower()
                shop = re.sub(r"^https?://", "", shop).strip("/")
                if shop and not SHOP_RE.match(shop):
                    raise ApiError(400, "bad_request", "Enter the store's myshopify.com address, for example my-store.myshopify.com.")
                conn.execute("DELETE FROM tenant_sources WHERE tenant_id = %s AND kind = 'shopify'", (tenant_id,))
                if shop:
                    conn.execute("INSERT INTO tenant_sources (tenant_id, kind, ref) VALUES (%s, 'shopify', %s)", (tenant_id, shop))
            if "countries" in data:
                rows, seen = [], set()
                if not isinstance(data["countries"], list) or len(data["countries"]) > 250:
                    raise ApiError(400, "bad_request", "The list of countries could not be read.")
                for item in data["countries"]:
                    code = str((item or {}).get("country", "")).strip().upper() if isinstance(item, dict) else ""
                    if not re.fullmatch(r"[A-Z]{2}", code):
                        raise ApiError(400, "bad_request", "Each country must be a two-letter code, for example US or GB.")
                    if code in seen:
                        raise ApiError(400, "bad_request", f"{code} is listed twice.")
                    seen.add(code)
                    rows.append((tenant_id, code, bool(item.get("split_by_region"))))
                conn.execute("DELETE FROM tenant_countries WHERE tenant_id = %s", (tenant_id,))
                for row in rows:
                    conn.execute("INSERT INTO tenant_countries (tenant_id, country, split_by_region) VALUES (%s, %s, %s)", row)
            audit(conn, user["id"], "tenant.updated", tenant=tenant_id, fields=sorted(k for k in data if k in ("name", "shop_domain", "countries")))
            return {"tenant": tenant_detail(conn, tenant_id)}

    @app.post("/api/admin/tenants/{tenant_id}/users")
    async def admin_add_user(tenant_id: str, request: Request, user=Depends(staff_user)):
        tenant_id = valid_uuid(tenant_id)
        email = str((await body(request)).get("email", "")).strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 254:
            raise ApiError(400, "bad_request", "Enter a valid email address.")
        with connect() as conn:
            tenant_detail(conn, tenant_id)
            existing = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
            temp = None
            if existing:
                user_id = existing["id"]
            else:
                temp = security.temp_password()
                user_id = conn.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                                       (email, security.hash_password(temp))).fetchone()["id"]
            conn.execute("INSERT INTO tenant_members (tenant_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (tenant_id, user_id))
            audit(conn, user["id"], "tenant.user_added", tenant=tenant_id, user=str(user_id), created=temp is not None)
            # The temporary password is returned this once and never stored in readable form.
            return {"tenant": tenant_detail(conn, tenant_id), "temporary_password": temp, "email": email}

    @app.delete("/api/admin/tenants/{tenant_id}/users/{user_id}")
    def admin_remove_user(tenant_id: str, user_id: str, user=Depends(staff_user)):
        tenant_id, user_id = valid_uuid(tenant_id), valid_uuid(user_id)
        with connect() as conn:
            conn.execute("DELETE FROM tenant_members WHERE tenant_id = %s AND user_id = %s", (tenant_id, user_id))
            audit(conn, user["id"], "tenant.user_removed", tenant=tenant_id, user=user_id)
            return {"tenant": tenant_detail(conn, tenant_id)}

    @app.post("/api/admin/users/{user_id}/reset-password")
    def admin_reset_password(user_id: str, user=Depends(staff_user)):
        user_id = valid_uuid(user_id)
        temp = security.temp_password()
        with connect() as conn:
            row = conn.execute(
                "UPDATE users SET password_hash = %s, must_change_password = true WHERE id = %s AND NOT is_staff RETURNING email",
                (security.hash_password(temp), user_id)).fetchone()
            if not row:
                raise ApiError(404, "not_found", "We could not find that login.")
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            audit(conn, user["id"], "user.password_reset", user=user_id)
            return {"email": row["email"], "temporary_password": temp}

    @app.put("/api/admin/users/{user_id}")
    async def admin_update_user(user_id: str, request: Request, user=Depends(staff_user)):
        user_id = valid_uuid(user_id)
        disabled = bool((await body(request)).get("disabled"))
        with connect() as conn:
            row = conn.execute("UPDATE users SET disabled = %s WHERE id = %s AND NOT is_staff RETURNING email",
                               (disabled, user_id)).fetchone()
            if not row:
                raise ApiError(404, "not_found", "We could not find that login.")
            if disabled:
                conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            audit(conn, user["id"], "user.disabled" if disabled else "user.enabled", user=user_id)
            return {"ok": True, "email": row["email"], "disabled": disabled}

    @app.get("/api/{rest:path}")
    def api_not_found(rest: str):
        raise ApiError(404, "not_found", "Not found.")

    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")
    return app


def _bootstrap_admin(settings):
    """Create the first staff login from environment variables, only while no login exists."""
    if not settings.bootstrap_email or not settings.bootstrap_password:
        return
    problem = security.password_problem(settings.bootstrap_password, settings.bootstrap_email)
    if problem:
        raise RuntimeError(f"BOOTSTRAP_ADMIN_PASSWORD is not acceptable: {problem}")
    with db.connect(settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        try:
            conn.execute("INSERT INTO users (email, password_hash, is_staff, must_change_password) VALUES (%s, %s, true, true)",
                         (settings.bootstrap_email, security.hash_password(settings.bootstrap_password)))
        except UniqueViolation:
            pass
