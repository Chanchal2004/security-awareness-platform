"""Simulation creation, tokens, sandbox send, event simulation, public tracking,
analytics, reports, audit logs and settings."""
import re
import uuid

import pytest
import requests
from conftest import API, BASE_URL


def uniq(p="TEST"):
    return f"{p}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="class")
def sim_ctx(client):
    """Create a sandbox simulation with 2 fresh recipients, landing page and form."""
    senders = client.get(f"{API}/senders", timeout=30).json()
    lps = client.get(f"{API}/landing-pages", timeout=30).json()
    forms = client.get(f"{API}/forms", timeout=30).json()
    assert senders and lps and forms, "seed data (sender/landing page/form) missing"
    emails = [f"{uniq('test.sim1')}@example.com".lower(), f"{uniq('test.sim2')}@example.com".lower()]
    payload = {
        "recipient_emails": emails,
        "sender_id": senders[0]["id"],
        "subject": "TEST_ Quarterly security document review",
        "body_html": "<p>Please review the attached secure document.</p>",
        "destination_url": "https://example.com/awareness",
        "tracking": {"open": True, "click": True, "landing": True, "form": True, "form_submit": True},
        "sender_sim": {"enabled": True, "from_email": "it-helpdesk@talbros-support.test",
                       "display_name": "Talbros IT Helpdesk"},
        "landing_page_id": lps[0]["id"],
        "form_id": forms[0]["id"],
        "mode": "sandbox",
    }
    r = client.post(f"{API}/simulations", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:400]
    sim = r.json()
    ctx = {"sim": sim, "emails": emails}
    yield ctx
    for e in emails:
        found = client.get(f"{API}/recipients", params={"search": e}, timeout=30).json()
        for x in found:
            client.delete(f"{API}/recipients/{x['id']}", timeout=30)


class TestSimulationCreate:
    def test_validation_errors(self, client):
        assert client.post(f"{API}/simulations", json={
            "subject": "  ", "body_html": "<p>x</p>", "recipient_emails": ["a@b.com"]},
            timeout=30).status_code == 400
        assert client.post(f"{API}/simulations", json={
            "subject": "s", "body_html": "  ", "recipient_emails": ["a@b.com"]},
            timeout=30).status_code == 400
        r = client.post(f"{API}/simulations", json={
            "subject": "s", "body_html": "<p>x</p>", "recipient_emails": ["a@b.com"],
            "destination_url": "javascript:alert(1)"}, timeout=30)
        assert r.status_code == 400 and "URL" in r.json()["detail"]
        r = client.post(f"{API}/simulations", json={
            "subject": "s", "body_html": "<p>x</p>", "recipient_emails": ["not-an-email"]}, timeout=30)
        assert r.status_code == 400 and "recipient" in r.json()["detail"].lower()

    def test_sim_created_with_auto_id_and_no_campaign_name(self, client, sim_ctx):
        sim = sim_ctx["sim"]
        assert re.fullmatch(r"SIM-\d{4}-\d{6}", sim["sim_id"]), sim["sim_id"]
        assert sim["status"] == "DRAFT"
        assert sim["mode"] == "sandbox"
        assert sim["recipient_count"] == 2
        assert "campaign_name" not in sim and "name" not in sim
        assert sim["sender_sim"]["enabled"] is True
        assert "_id" not in sim

        got = client.get(f"{API}/simulations/{sim['id']}", timeout=30)
        assert got.status_code == 200
        g = got.json()
        assert g["sim_id"] == sim["sim_id"]
        assert g["stats"]["recipients"] == 2
        assert g["stats"]["sent"] == 0

        assert client.get(f"{API}/simulations/{uuid.uuid4()}", timeout=30).status_code == 404

    def test_unique_32char_tokens(self, client, sim_ctx):
        recs = client.get(f"{API}/simulations/{sim_ctx['sim']['id']}/recipients", timeout=30).json()
        assert len(recs) == 2
        tokens = [r["token"] for r in recs]
        assert len(set(tokens)) == 2, "tokens are not unique per recipient"
        for t in tokens:
            assert len(t) == 32, f"token length {len(t)} != 32"
        assert all("_id" not in r for r in recs)


class TestSandboxSendAndTracking:
    def test_send_test_sandbox(self, client, sim_ctx):
        r = client.post(f"{API}/simulations/{sim_ctx['sim']['id']}/test",
                        json={"email": "qa-tester@example.com"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "SENT", r.json()

    def test_send_now_sandbox_records_email_sent(self, client, sim_ctx):
        sid = sim_ctx["sim"]["id"]
        r = client.post(f"{API}/simulations/{sid}/send", timeout=90)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["sent"] == 2 and d["mode"] == "sandbox"

        sim = client.get(f"{API}/simulations/{sid}", timeout=30).json()
        assert sim["status"] == "RUNNING"
        assert sim["stats"]["sent"] == 2

        recs = client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
        assert all(x["sent"] is True and x["delivery_status"] == "SANDBOX_SENT" for x in recs)
        tl = client.get(f"{API}/simulations/{sid}/recipients/{recs[0]['id']}/timeline", timeout=30).json()
        assert [e["event_type"] for e in tl] == ["EMAIL_SENT"]

    def test_simulate_event_endpoint(self, client, sim_ctx):
        sid = sim_ctx["sim"]["id"]
        recs = client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
        target = recs[0]
        r = client.post(f"{API}/simulations/{sid}/simulate-event",
                        json={"recipient_id": target["id"], "event_type": "EMAIL_OPENED"}, timeout=30)
        assert r.status_code == 200
        after = [x for x in client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
                 if x["id"] == target["id"]][0]
        assert after["open_count"] == target.get("open_count", 0) + 1
        assert after["first_open"] and after["last_activity"]

        assert client.post(f"{API}/simulations/{sid}/simulate-event",
                           json={"recipient_id": target["id"], "event_type": "NOPE"},
                           timeout=30).status_code == 400
        assert client.post(f"{API}/simulations/{sid}/simulate-event",
                           json={"recipient_id": str(uuid.uuid4()), "event_type": "EMAIL_OPENED"},
                           timeout=30).status_code == 404

    def test_public_tracking_no_auth(self, client, sim_ctx):
        """Open pixel, click redirect, landing page, form start/submit — all unauthenticated."""
        sid = sim_ctx["sim"]["id"]
        recs = client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
        target = recs[1]
        token = target["token"]
        anon = requests.Session()

        # open pixel
        before = target.get("open_count", 0)
        px = anon.get(f"{API}/track/open/{token}.png", timeout=30)
        assert px.status_code == 200
        assert px.headers["content-type"] == "image/png"
        assert px.content[:8] == b"\x89PNG\r\n\x1a\n"
        cur = [x for x in client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
               if x["id"] == target["id"]][0]
        assert cur["open_count"] == before + 1

        # click -> 307 redirect to landing page route
        clk = anon.get(f"{API}/track/click/{token}", timeout=30, allow_redirects=False)
        assert clk.status_code in (302, 307), clk.status_code
        assert f"/lp/{token}" in clk.headers["location"], clk.headers["location"]
        cur = [x for x in client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
               if x["id"] == target["id"]][0]
        assert cur["click_count"] >= 1 and cur["first_click"]

        # public landing payload
        lp = anon.get(f"{API}/public/landing/{token}", timeout=30)
        assert lp.status_code == 200, lp.text[:300]
        body = lp.json()
        assert body["landing_page"] and body["landing_page"]["title"]
        assert body["form_enabled"] is True and body["form"]["fields"]

        # form start
        assert anon.post(f"{API}/public/form-start/{token}", timeout=30).status_code == 200
        # form submit — banned key must not be persisted
        sub = anon.post(f"{API}/public/form-submit/{token}",
                        json={"responses": {"Full Name": "QA Tester", "password": "hunter2"}}, timeout=30)
        assert sub.status_code == 200

        cur = [x for x in client.get(f"{API}/simulations/{sid}/recipients", timeout=30).json()
               if x["id"] == target["id"]][0]
        assert cur["landing_visited"] is True
        assert cur["form_started"] is True
        assert cur["form_submitted"] is True and cur["form_submitted_at"]

        # bad token handling
        assert anon.get(f"{API}/track/open/{'x' * 32}.png", timeout=30).status_code == 200
        assert anon.get(f"{API}/public/landing/{'x' * 32}", timeout=30).status_code == 404

        # timeline chronological with expected types
        tl = client.get(f"{API}/simulations/{sid}/recipients/{target['id']}/timeline", timeout=30).json()
        types = [e["event_type"] for e in tl]
        for expected in ("EMAIL_SENT", "EMAIL_OPENED", "LINK_CLICKED",
                         "LANDING_PAGE_VISITED", "FORM_STARTED", "FORM_SUBMITTED"):
            assert expected in types, f"{expected} missing from timeline {types}"
        stamps = [e["timestamp"] for e in tl]
        assert stamps == sorted(stamps), "timeline not chronological"
        assert all("_id" not in e for e in tl)

        # credentials never stored
        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values("/app/backend/.env")
        mc = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=8000)
        subs = list(mc[env["DB_NAME"]].form_submissions.find({"recipient_id": target["id"]}))
        mc.close()
        assert subs, "form submission not stored"
        assert not any("password" in str(k).lower() for k in subs[-1]["responses"]), subs[-1]["responses"]
        assert subs[-1]["responses"].get("Full Name") == "QA Tester"

    def test_simulate_full_pipeline(self, client, sim_ctx):
        sid = sim_ctx["sim"]["id"]
        r = client.post(f"{API}/simulations/{sid}/simulate-full", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["recipients"] == 2
        sim = client.get(f"{API}/simulations/{sid}", timeout=30).json()
        assert sim["status"] == "COMPLETED"
        assert sim["stats"]["opened"] >= 1

    def test_status_update(self, client, sim_ctx):
        sid = sim_ctx["sim"]["id"]
        assert client.put(f"{API}/simulations/{sid}/status", json={"status": "PAUSED"}, timeout=30).status_code == 200
        assert client.get(f"{API}/simulations/{sid}", timeout=30).json()["status"] == "PAUSED"
        assert client.put(f"{API}/simulations/{sid}/status", json={"status": "BOGUS"},
                          timeout=30).status_code == 400


class TestAnalyticsReportsAdmin:
    def test_dashboard(self, client):
        r = client.get(f"{API}/analytics/dashboard", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("total_simulations", "total_recipients", "emails_sent", "observed_opens",
                  "link_clicks", "landing_page_visits", "forms_started", "forms_submitted"):
            assert k in d["cards"] and isinstance(d["cards"][k], int)
        for k in ("open_rate", "click_rate", "landing_rate", "form_start_rate", "form_submission_rate"):
            assert isinstance(d["rates"][k], (int, float))
        assert isinstance(d["activity"], list) and isinstance(d["recent_events"], list)
        assert all("_id" not in e for e in d["recent_events"])
        for s in d["recent_simulations"]:
            assert "stats" in s and "sim_id" in s

    def test_department_analytics(self, client):
        r = client.get(f"{API}/analytics/departments", timeout=60)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and rows
        assert any(x["department"] == "No Department" for x in rows)
        for x in rows:
            assert set(("recipients", "sent", "opened", "clicked", "click_rate")).issubset(x)

    def test_recipient_analytics_filters(self, client):
        base = client.get(f"{API}/analytics/recipients", timeout=60)
        assert base.status_code == 200
        opened = client.get(f"{API}/analytics/recipients", params={"filter": "opened"}, timeout=60).json()
        assert all(x["open_count"] > 0 for x in opened)
        notop = client.get(f"{API}/analytics/recipients", params={"filter": "not_opened"}, timeout=60).json()
        assert all(x["open_count"] == 0 for x in notop)
        clicked = client.get(f"{API}/analytics/recipients", params={"filter": "clicked"}, timeout=60).json()
        assert all(x["click_count"] > 0 for x in clicked)
        subm = client.get(f"{API}/analytics/recipients", params={"filter": "form_submitted"}, timeout=60).json()
        assert all(x["form_submitted"] for x in subm)

    @pytest.mark.parametrize("path,header", [
        ("/reports/simulation-summary", "simulation_id"),
        ("/reports/recipient", "recipient_email"),
        ("/reports/department", "department"),
        ("/reports/event", "event_type"),
    ])
    def test_csv_reports(self, client, path, header):
        r = client.get(f"{API}{path}", timeout=90)
        assert r.status_code == 200, r.text[:200]
        assert "text/csv" in r.headers["content-type"]
        assert "attachment; filename=" in r.headers.get("content-disposition", "")
        first_line = r.text.splitlines()[0]
        assert header in first_line, first_line

    def test_audit_logs_and_filter(self, client):
        # generate auditable actions in this test so the assertion is order-independent
        email = f"{uniq('test.audit')}@example.com".lower()
        rid = client.post(f"{API}/recipients", json={"email": email}, timeout=30).json()["id"]
        sim = client.post(f"{API}/simulations", json={
            "recipient_ids": [rid], "subject": "TEST_ audit sim",
            "body_html": "<p>x</p>", "mode": "sandbox"}, timeout=60).json()
        client.post(f"{API}/simulations/{sim['id']}/send", timeout=60)
        client.get(f"{API}/reports/event", timeout=60)

        r = client.get(f"{API}/audit-logs", timeout=60)
        assert r.status_code == 200
        logs = r.json()
        assert logs and all("_id" not in x for x in logs)
        actions = {x["action"] for x in logs}
        client.delete(f"{API}/recipients/{rid}", timeout=30)
        for expected in ("LOGIN", "RECIPIENT_CREATED", "SIMULATION_CREATED",
                         "SIMULATION_LAUNCHED", "REPORT_EXPORTED"):
            assert expected in actions, f"{expected} not in audit actions {sorted(actions)}"
        filtered = client.get(f"{API}/audit-logs", params={"action": "LOGIN"}, timeout=60).json()
        assert filtered and all(x["action"] == "LOGIN" for x in filtered)
        stamps = [x["timestamp"] for x in logs]
        assert stamps == sorted(stamps, reverse=True)

    def test_settings_retention(self, client):
        cur = client.get(f"{API}/settings", timeout=30)
        assert cur.status_code == 200
        original = cur.json().get("retention_days", 90)
        for days in (30, 180, 365, original):
            r = client.put(f"{API}/settings", json={"retention_days": days, "default_mode": "sandbox"}, timeout=30)
            assert r.status_code == 200
            assert client.get(f"{API}/settings", timeout=30).json()["retention_days"] == days
        bad = client.put(f"{API}/settings", json={"retention_days": 45, "default_mode": "sandbox"}, timeout=30)
        assert bad.status_code == 400

    def test_expired_simulations_count(self, client):
        r = client.get(f"{API}/settings/expired-simulations", timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["count"], int) and d["retention_days"] in (30, 90, 180, 365)
        assert d["count"] == len(d["simulations"])


class TestLiveGuardrails:
    def test_live_with_sender_sim_refused(self, client):
        """Live mode + sender identity simulation must be refused with 422 (by design)."""
        email = f"{uniq('test.live')}@example.com".lower()
        sim = client.post(f"{API}/simulations", json={
            "recipient_emails": [email], "subject": "TEST_ live guardrail",
            "body_html": "<p>hello</p>", "mode": "live",
            "sender_sim": {"enabled": True, "from_email": "spoof@evil.test", "display_name": "Spoof"},
        }, timeout=60)
        assert sim.status_code == 200, sim.text[:300]
        sid = sim.json()["id"]
        r = client.post(f"{API}/simulations/{sid}/send", timeout=60)
        assert r.status_code == 422, r.status_code
        assert "sandbox" in r.json()["detail"].lower()
        t = client.post(f"{API}/simulations/{sid}/test", json={"email": "qa@example.com"}, timeout=60)
        assert t.status_code == 200 and t.json()["status"] == "FAILED"
        for x in client.get(f"{API}/recipients", params={"search": email}, timeout=30).json():
            client.delete(f"{API}/recipients/{x['id']}", timeout=30)
