"""Tests for the new PUT /api/simulations/{sid} endpoint (stale-draft fix)."""
import time

import pytest


@pytest.fixture(scope="class")
def created_sim_ids():
    return []


@pytest.fixture(scope="class", autouse=True)
def cleanup(client, api_base, created_sim_ids):
    yield
    for sid in created_sim_ids:
        client.delete(f"{api_base}/simulations/{sid}", timeout=30)


class TestSimulationUpdate:
    def _payload(self, emails, subject, body="<p>Body</p>"):
        return {
            "recipient_emails": emails,
            "sender_id": None,
            "subject": subject,
            "body_html": body,
            "destination_url": "https://talbros.test/awareness",
            "tracking": {"open": True, "click": True, "landing": True, "form": True, "form_submit": True},
            "sender_sim": {"enabled": False, "from_email": "", "display_name": ""},
            "landing_page_id": None,
            "form_id": None,
            "mode": "sandbox",
            "scheduled_at": None,
        }

    def test_update_draft_persists_subject_and_recipients(self, client, api_base, created_sim_ids):
        ts = int(time.time())
        e1 = f"test_put1_{ts}@example.test"
        e2 = f"test_put2_{ts}@example.test"
        r = client.post(f"{api_base}/simulations", json=self._payload([e1], f"TEST_orig {ts}"), timeout=30)
        assert r.status_code in (200, 201), r.text
        sim = r.json()
        sid = sim["id"]
        created_sim_ids.append(sid)
        assert sim["subject"] == f"TEST_orig {ts}"
        assert sim["recipient_count"] == 1

        upd = client.put(f"{api_base}/simulations/{sid}",
                         json=self._payload([e1, e2], f"TEST_edited {ts}", "<p>Hello Team Members</p>"), timeout=30)
        assert upd.status_code == 200, upd.text
        d = upd.json()
        assert d["subject"] == f"TEST_edited {ts}"
        assert d["recipient_count"] == 2
        assert "_id" not in d

        # GET to verify persistence
        g = client.get(f"{api_base}/simulations/{sid}", timeout=30)
        assert g.status_code == 200
        det = g.json()
        sub = det.get("subject") or det.get("simulation", {}).get("subject")
        assert sub == f"TEST_edited {ts}", det
        body_html = det.get("body_html") or det.get("simulation", {}).get("body_html")
        assert "Hello Team Members" in body_html
        rr = client.get(f"{api_base}/simulations/{sid}/recipients", timeout=30)
        assert rr.status_code == 200
        recips = rr.json()
        emails = sorted(x["email"] for x in recips)
        assert emails == sorted([e1, e2]), emails
        # tokens unique and 32 chars
        tokens = [x["token"] for x in recips]
        assert len(set(tokens)) == len(tokens)
        assert all(len(t) == 32 for t in tokens), tokens

    def test_update_after_send_rejected(self, client, api_base, created_sim_ids):
        ts = int(time.time())
        e1 = f"test_put3_{ts}@example.test"
        r = client.post(f"{api_base}/simulations", json=self._payload([e1], f"TEST_sent {ts}"), timeout=30)
        sid = r.json()["id"]
        created_sim_ids.append(sid)
        s = client.post(f"{api_base}/simulations/{sid}/send", timeout=60)
        assert s.status_code == 200, s.text
        upd = client.put(f"{api_base}/simulations/{sid}", json=self._payload([e1], f"TEST_nope {ts}"), timeout=30)
        assert upd.status_code == 400, upd.text

    def test_update_nonexistent_404(self, client, api_base):
        upd = client.put(f"{api_base}/simulations/does-not-exist",
                         json=self._payload(["test_put4@example.test"], "TEST_x"), timeout=30)
        assert upd.status_code == 404

    def test_update_validation_errors(self, client, api_base, created_sim_ids):
        ts = int(time.time())
        e1 = f"test_put5_{ts}@example.test"
        r = client.post(f"{api_base}/simulations", json=self._payload([e1], f"TEST_val {ts}"), timeout=30)
        sid = r.json()["id"]
        created_sim_ids.append(sid)
        # empty subject
        bad = self._payload([e1], "   ")
        assert client.put(f"{api_base}/simulations/{sid}", json=bad, timeout=30).status_code == 400
        # no recipients
        bad2 = self._payload([], f"TEST_val {ts}")
        assert client.put(f"{api_base}/simulations/{sid}", json=bad2, timeout=30).status_code == 400

    def test_update_requires_auth(self, anon_client, api_base):
        r = anon_client.put(f"{api_base}/simulations/whatever",
                            json=self._payload(["a@example.test"], "TEST_auth"), timeout=30)
        assert r.status_code in (401, 403)
