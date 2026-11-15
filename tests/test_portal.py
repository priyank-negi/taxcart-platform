"""Portal tests. Need a Postgres to run against:

    TEST_DATABASE_URL=postgresql://user@host/dbname pytest

The database is wiped at the start of each test. The tax engine is replaced by a fake.
"""
import os
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from portal import config, engine, security
from portal.app import create_app

DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL is not set")

ADMIN = ("admin@taxcart.test", "first-admin-password-1")
H = {"X-Requested-With": "taxcart", "Origin": "http://localhost"}

SUMMARY = {
    "shop": "shop-a.myshopify.com", "date_from": "2026-10-01", "date_to": "2026-10-31", "timezone": "UTC",
    "countries": ["US", "GB"], "split": ["US"], "currencies": ["USD"],
    "totals": {"orders": 8, "net_sales": "8929.8000", "tax_charged": "738.3600", "refunded_tax": "20.0000",
               "refund_tax_adjustments": "0.0000", "net_tax": "718.3600", "channel_liable_tax": "0.0000"},
    "by_jurisdiction": [
        {"country": "GB", "province": None, "orders": 2, "net_sales": "200.0000", "tax_charged": "40.0000",
         "refunds": 1, "refunded_tax": "20.0000", "refund_tax_adjustments": "0.0000", "net_tax": "20.0000"},
        {"country": "US", "province": "CA", "orders": 1, "net_sales": "100.0000", "tax_charged": "0.0000",
         "refunds": 0, "refunded_tax": "0.0000", "refund_tax_adjustments": "0.0000", "net_tax": "0.0000",
         "channel_liable_tax": "7.2500"},
        {"country": "US", "province": "TX", "orders": 5, "net_sales": "8629.8000", "tax_charged": "698.3600",
         "refunds": 0, "refunded_tax": "0.0000", "refund_tax_adjustments": "0.0000", "net_tax": "698.3600"},
    ],
    "by_component": [
        {"country": "GB", "province": None, "title": "GB VAT", "rate": "0.200000", "orders": 2,
         "implied_taxable_sales": "200.00", "tax_collected": "40.0000"},
        {"country": "US", "province": "TX", "title": "Santa Rosa City Tax", "rate": "0.017500", "orders": 5,
         "implied_taxable_sales": "8729.14", "tax_collected": "152.7600"},
        {"country": "US", "province": "TX", "title": "Texas State Tax", "rate": "0.062500", "orders": 5,
         "implied_taxable_sales": "8729.60", "tax_collected": "545.6000"},
    ],
    "outside_selection": [{"country": "CA", "orders": 3, "net_sales": "500.0000", "tax_charged": "0.0000"}],
    "exceptions": {"missing_destination": [], "refund_mismatch": [],
                   "untaxed": [{"name": "#1002", "order_id": 1, "country": "US", "province": "CA"}]},
}


class Portal:
    def __init__(self):
        with psycopg.connect(DB) as conn:
            conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        self.engine_calls = []
        self.engine_error = None
        settings = config.Settings(
            database_url=DB, engine_url="http://engine.invalid", engine_key="k", origins=("http://localhost",),
            session_days=7, cookie_secure=False, bootstrap_email=ADMIN[0], bootstrap_password=ADMIN[1])

        def fake_fetch(_settings, shop, date_from, date_to, countries, split):
            self.engine_calls.append((shop, date_from, date_to, countries, split))
            if self.engine_error:
                raise self.engine_error
            return SUMMARY

        self.app = create_app(settings, fetch_summary=fake_fetch)

    def client(self):
        return TestClient(self.app, base_url="http://localhost")

    def staff(self):
        """A signed-in staff client that has already replaced the bootstrap password."""
        c = self.client()
        assert c.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H).status_code == 200
        r = c.post("/api/auth/change-password", headers=H,
                   json={"current_password": ADMIN[1], "new_password": "a-much-better-password"})
        assert r.status_code == 200, r.text
        return c

    def client_login(self, staff, tenant_id, email):
        """Staff adds a login; the person signs in and chooses a password. Returns their client."""
        r = staff.post(f"/api/admin/tenants/{tenant_id}/users", json={"email": email}, headers=H).json()
        c = self.client()
        assert c.post("/api/auth/login", json={"email": email, "password": r["temporary_password"]}, headers=H).status_code == 200
        assert c.post("/api/auth/change-password", headers=H,
                      json={"current_password": r["temporary_password"], "new_password": "client-own-password-9"}).status_code == 200
        return c


@pytest.fixture()
def portal():
    return Portal()


def make_tenant(staff, name="Acme Pty Ltd", shop="shop-a.myshopify.com", countries=(("US", True), ("GB", False))):
    tid = staff.post("/api/admin/tenants", json={"name": name}, headers=H).json()["tenant"]["id"]
    r = staff.put(f"/api/admin/tenants/{tid}", headers=H, json={
        "shop_domain": shop, "countries": [{"country": c, "split_by_region": s} for c, s in countries]})
    assert r.status_code == 200, r.text
    return tid


REPORT = "/api/reports/sales-tax?tenant={}&date_from=2026-10-01&date_to=2026-10-31"


# ---------------------------------------------------------------- sign-in
def test_signed_out_requests_are_refused(portal):
    c = portal.client()
    for path in ("/api/session", "/api/admin/tenants", REPORT.format("x")):
        assert c.get(path).status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(portal):
    c = portal.client()
    a = c.post("/api/auth/login", json={"email": ADMIN[0], "password": "nope-nope-nope"}, headers=H)
    b = c.post("/api/auth/login", json={"email": "nobody@taxcart.test", "password": "nope-nope-nope"}, headers=H)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    assert "tc_session" not in c.cookies


def test_first_sign_in_forces_a_password_change(portal):
    c = portal.client()
    r = c.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H)
    assert r.json()["must_change_password"] is True
    assert c.get("/api/session").json()["tenants"] == []
    assert c.get("/api/admin/tenants").status_code == 403
    assert c.get("/api/admin/tenants").json()["error"]["code"] == "password_change_required"
    weak = c.post("/api/auth/change-password", json={"current_password": ADMIN[1], "new_password": "short"}, headers=H)
    assert weak.status_code == 400
    wrong = c.post("/api/auth/change-password", json={"current_password": "x", "new_password": "a-much-better-password"}, headers=H)
    assert wrong.status_code == 400
    ok = c.post("/api/auth/change-password", json={"current_password": ADMIN[1], "new_password": "a-much-better-password"}, headers=H)
    assert ok.status_code == 200
    assert c.get("/api/admin/tenants").status_code == 200
    # the old password no longer works
    assert portal.client().post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H).status_code == 401


def test_session_cookie_is_http_only_and_logout_ends_it(portal):
    c = portal.client()
    r = c.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    token = c.cookies["tc_session"]
    assert c.post("/api/auth/logout", headers=H).status_code == 200
    stale = portal.client()
    stale.cookies.set("tc_session", token)
    assert stale.get("/api/session").status_code == 401


def test_changing_password_signs_out_other_devices(portal):
    first = portal.client()
    first.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H)
    second = portal.client()
    second.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H)
    second.post("/api/auth/change-password", json={"current_password": ADMIN[1], "new_password": "a-much-better-password"}, headers=H)
    assert first.get("/api/session").status_code == 401
    assert second.get("/api/session").status_code == 200


def test_too_many_wrong_passwords_locks_the_address_for_a_while(portal):
    c = portal.client()
    for _ in range(security.MAX_FAILS_PER_EMAIL):
        assert c.post("/api/auth/login", json={"email": ADMIN[0], "password": "wrong-wrong-wrong"}, headers=H).status_code == 401
    # even the right password is refused while locked
    assert c.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, headers=H).status_code == 429


def test_changes_need_our_header_and_origin(portal):
    c = portal.client()
    creds = {"email": ADMIN[0], "password": ADMIN[1]}
    assert c.post("/api/auth/login", json=creds).status_code == 403
    assert c.post("/api/auth/login", json=creds, headers={"X-Requested-With": "taxcart", "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/auth/login", json=creds, headers=H).status_code == 200


def test_passwords_are_stored_hashed(portal):
    with psycopg.connect(DB) as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored.startswith("scrypt$") and ADMIN[1] not in stored


def test_bootstrap_runs_only_when_there_are_no_logins(portal):
    staff = portal.staff()
    settings = config.Settings(database_url=DB, engine_url="http://e", engine_key="k", origins=("http://localhost",),
                               session_days=7, cookie_secure=False, bootstrap_email="second@taxcart.test",
                               bootstrap_password="another-long-password-2")
    create_app(settings)
    with psycopg.connect(DB) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert staff.get("/api/session").status_code == 200


# ---------------------------------------------------------------- staff setup
def test_staff_sets_up_a_client(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    t = staff.get("/api/admin/tenants").json()["tenants"][0]
    assert t["id"] == tid and t["shop_domain"] == "shop-a.myshopify.com"
    assert t["countries"] == [{"country": "US", "split_by_region": True}, {"country": "GB", "split_by_region": False}]
    added = staff.post(f"/api/admin/tenants/{tid}/users", json={"email": "Owner@Acme.test"}, headers=H).json()
    assert added["email"] == "owner@acme.test" and len(added["temporary_password"]) >= 12
    assert [u["email"] for u in added["tenant"]["users"]] == ["owner@acme.test"]
    # adding the same person to a second client does not issue a new password
    other = make_tenant(staff, name="Beta Ltd", shop="shop-b.myshopify.com")
    again = staff.post(f"/api/admin/tenants/{other}/users", json={"email": "owner@acme.test"}, headers=H).json()
    assert again["temporary_password"] is None


@pytest.mark.parametrize("payload", [
    {"shop_domain": "evil.example.com"}, {"shop_domain": "a b.myshopify.com"},
    {"countries": [{"country": "USA"}]}, {"countries": [{"country": "US"}, {"country": "us"}]},
    {"countries": "US"}, {"name": ""},
])
def test_bad_setup_values_are_rejected(portal, payload):
    staff = portal.staff()
    tid = make_tenant(staff)
    assert staff.put(f"/api/admin/tenants/{tid}", json=payload, headers=H).status_code == 400
    # and nothing was changed
    t = staff.get("/api/admin/tenants").json()["tenants"][0]
    assert t["shop_domain"] == "shop-a.myshopify.com" and len(t["countries"]) == 2


def test_clients_cannot_use_staff_endpoints(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    c = portal.client_login(staff, tid, "owner@acme.test")
    assert c.get("/api/admin/tenants").status_code == 403
    assert c.post("/api/admin/tenants", json={"name": "X"}, headers=H).status_code == 403
    assert c.put(f"/api/admin/tenants/{tid}", json={"countries": []}, headers=H).status_code == 403
    assert c.post(f"/api/admin/tenants/{tid}/users", json={"email": "x@y.test"}, headers=H).status_code == 403


def test_reset_and_disable(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    c = portal.client_login(staff, tid, "owner@acme.test")
    uid = staff.get("/api/admin/tenants").json()["tenants"][0]["users"][0]["id"]
    reset = staff.post(f"/api/admin/users/{uid}/reset-password", headers=H).json()
    assert c.get("/api/session").status_code == 401            # signed out everywhere
    fresh = portal.client()
    assert fresh.post("/api/auth/login", json={"email": "owner@acme.test", "password": reset["temporary_password"]}, headers=H).json()["must_change_password"] is True
    assert staff.put(f"/api/admin/users/{uid}", json={"disabled": True}, headers=H).status_code == 200
    assert fresh.get("/api/session").status_code == 401
    assert portal.client().post("/api/auth/login", json={"email": "owner@acme.test", "password": reset["temporary_password"]}, headers=H).status_code == 401


def test_staff_logins_cannot_be_reset_or_disabled_here(portal):
    staff = portal.staff()
    with psycopg.connect(DB) as conn:
        admin_id = str(conn.execute("SELECT id FROM users").fetchone()[0])
    assert staff.post(f"/api/admin/users/{admin_id}/reset-password", headers=H).status_code == 404
    assert staff.put(f"/api/admin/users/{admin_id}", json={"disabled": True}, headers=H).status_code == 404


# ---------------------------------------------------------------- report
def test_client_sees_their_report_without_review_items(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    c = portal.client_login(staff, tid, "owner@acme.test")
    r = c.get(REPORT.format(tid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert portal.engine_calls[-1] == ("shop-a.myshopify.com", date(2026, 10, 1), date(2026, 10, 31), ["US", "GB"], ["US"])
    assert body["status"] == "ready" and body["currency"] == "USD" and body["tenant"]["name"] == "Acme Pty Ltd"
    assert "review" not in body and "shop" not in body and "exceptions" not in str(body)
    us, gb = body["countries"]
    assert us["country"] == "US" and us["orders"] == 6 and us["net_tax"] == "698.3600"
    assert [x["region"] for x in us["regions"]] == ["CA", "TX"]
    tx = us["regions"][1]
    assert [(k["title"], k["tax"]) for k in tx["components"]] == [("Santa Rosa City Tax", "152.7600"), ("Texas State Tax", "545.6000")]
    assert us["regions"][0]["components"] == []
    assert us["regions"][0]["marketplace_tax"] == "7.2500" and us["marketplace_tax"] == "7.2500" and gb["marketplace_tax"] == "0"
    assert gb["country"] == "GB" and "regions" not in gb and gb["net_tax"] == "20.0000"
    assert gb["components"] == [{"title": "GB VAT", "rate": "0.200000", "taxable_sales": "200.00", "tax": "40.0000"}]
    assert body["totals"]["net_tax"] == "718.3600"


def test_staff_also_get_review_items(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    body = staff.get(REPORT.format(tid)).json()
    assert body["review"]["exceptions"]["untaxed"][0]["name"] == "#1002"
    assert body["review"]["outside_selection"][0]["country"] == "CA"


def test_a_configured_country_with_no_sales_still_appears(portal):
    staff = portal.staff()
    tid = make_tenant(staff, countries=(("US", True), ("GB", False), ("DE", False)))
    de = staff.get(REPORT.format(tid)).json()["countries"][1]
    assert de["country"] == "DE" and de["orders"] == 0 and de["net_tax"] == "0" and de["components"] == []


def test_clients_cannot_see_another_clients_report(portal):
    staff = portal.staff()
    mine = make_tenant(staff)
    theirs = make_tenant(staff, name="Beta Ltd", shop="shop-b.myshopify.com")
    c = portal.client_login(staff, mine, "owner@acme.test")
    calls = len(portal.engine_calls)
    for other in (theirs, "00000000-0000-0000-0000-000000000000", "not-an-id"):
        r = c.get(REPORT.format(other))
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert len(portal.engine_calls) == calls                   # the engine was never asked
    assert [t["name"] for t in c.get("/api/session").json()["tenants"]] == ["Acme Pty Ltd"]
    assert len(staff.get("/api/session").json()["tenants"]) == 2


def test_report_explains_unfinished_setup(portal):
    staff = portal.staff()
    tid = staff.post("/api/admin/tenants", json={"name": "New Co"}, headers=H).json()["tenant"]["id"]
    body = staff.get(REPORT.format(tid)).json()
    assert body["status"] == "not_set_up" and body["missing"] == ["data_source", "countries"]
    assert portal.engine_calls == []


def test_report_rejects_bad_periods(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    assert staff.get(f"/api/reports/sales-tax?tenant={tid}&date_from=2026-11-01&date_to=2026-10-01").status_code == 400
    assert staff.get(f"/api/reports/sales-tax?tenant={tid}&date_from=2024-01-01&date_to=2026-10-01").status_code == 400
    r = staff.get(f"/api/reports/sales-tax?tenant={tid}&date_from=yesterday&date_to=2026-10-01")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_engine_trouble_is_reported_plainly(portal):
    staff = portal.staff()
    tid = make_tenant(staff)
    portal.engine_error = engine.EngineError("The reporting service is starting up. Please try again in a minute.", 503)
    r = staff.get(REPORT.format(tid))
    assert r.status_code == 503 and "starting up" in r.json()["error"]["message"]


# ---------------------------------------------------------------- pages
def test_pages_are_served_with_security_headers(portal):
    r = portal.client().get("/")
    assert r.status_code == 200 and "Taxcart" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"
    api = portal.client().get("/api/session")
    assert api.headers["cache-control"] == "no-store"
    assert portal.client().get("/api/nope").status_code == 404
