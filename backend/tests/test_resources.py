"""Departments, Recipients (single/bulk/CSV), Senders, Landing Pages, Awareness Forms."""
import uuid

import pytest
from conftest import API


def uniq(prefix="TEST"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestDepartments:
    created = []

    def test_create_list_rename_delete(self, client):
        name = uniq("TEST_Dept")
        r = client.post(f"{API}/departments", json={"name": name}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["name"] == name and d["recipient_count"] == 0
        did = d["id"]
        self.created.append(did)

        lst = client.get(f"{API}/departments", timeout=30).json()
        match = [x for x in lst if x["id"] == did]
        assert match and "recipient_count" in match[0]
        assert all("_id" not in x for x in lst)

        # duplicate rejected
        dup = client.post(f"{API}/departments", json={"name": name}, timeout=30)
        assert dup.status_code == 409, dup.status_code

        # rename + verify persistence
        new_name = name + "_R"
        assert client.put(f"{API}/departments/{did}", json={"name": new_name}, timeout=30).status_code == 200
        lst = client.get(f"{API}/departments", timeout=30).json()
        assert [x for x in lst if x["id"] == did][0]["name"] == new_name

        # empty name rejected
        assert client.post(f"{API}/departments", json={"name": "   "}, timeout=30).status_code == 400

        # delete + verify removal
        assert client.delete(f"{API}/departments/{did}", timeout=30).status_code == 200
        self.created.remove(did)
        lst = client.get(f"{API}/departments", timeout=30).json()
        assert not [x for x in lst if x["id"] == did]
        assert client.delete(f"{API}/departments/{did}", timeout=30).status_code == 404


class TestRecipients:
    ids = []
    dept_ids = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, client):
        yield
        for rid in self.ids:
            client.delete(f"{API}/recipients/{rid}", timeout=30)
        for did in self.dept_ids:
            client.delete(f"{API}/departments/{did}", timeout=30)

    def test_create_email_only(self, client):
        email = f"{uniq('test.only')}@example.com".lower()
        r = client.post(f"{API}/recipients", json={"email": email}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["email"] == email and d["display_name"] == "" and d["department"] == ""
        assert d["enabled"] is True and isinstance(d["id"], str)
        self.ids.append(d["id"])

        # GET persistence
        lst = client.get(f"{API}/recipients", params={"search": email}, timeout=30).json()
        assert any(x["email"] == email for x in lst)
        assert all("_id" not in x for x in lst)

        # duplicate
        assert client.post(f"{API}/recipients", json={"email": email}, timeout=30).status_code == 409
        # invalid email
        assert client.post(f"{API}/recipients", json={"email": "not-an-email"}, timeout=30).status_code == 422

    def test_update_toggle_delete(self, client):
        email = f"{uniq('test.upd')}@example.com".lower()
        rid = client.post(f"{API}/recipients", json={"email": email}, timeout=30).json()["id"]
        self.ids.append(rid)

        dept = uniq("TEST_RDept")
        self.dept_ids.append(client.post(f"{API}/departments", json={"name": dept}, timeout=30).json()["id"])

        r = client.put(f"{API}/recipients/{rid}", json={
            "email": email, "display_name": "QA Person", "department": dept, "enabled": False}, timeout=30)
        assert r.status_code == 200
        got = [x for x in client.get(f"{API}/recipients", params={"search": email}, timeout=30).json()
               if x["id"] == rid][0]
        assert got["display_name"] == "QA Person" and got["department"] == dept and got["enabled"] is False

        # department filter
        filt = client.get(f"{API}/recipients", params={"department": dept}, timeout=30).json()
        assert [x["id"] for x in filt] == [rid]

        # dept recipient_count reflected
        depts = client.get(f"{API}/departments", timeout=30).json()
        assert [x for x in depts if x["name"] == dept][0]["recipient_count"] == 1

        assert client.delete(f"{API}/recipients/{rid}", timeout=30).status_code == 200
        self.ids.remove(rid)
        assert not client.get(f"{API}/recipients", params={"search": email}, timeout=30).json()
        assert client.delete(f"{API}/recipients/{rid}", timeout=30).status_code == 404

    def test_bulk_add_validation(self, client):
        good1 = f"{uniq('test.b1')}@example.com".lower()
        good2 = f"{uniq('test.b2')}@example.com".lower()
        r = client.post(f"{API}/recipients/bulk", json={
            "emails": [good1, good2, good1, "bad-email", ""]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["valid"] == 2 and d["imported"] == 2
        assert d["invalid"] == 1 and "bad-email" in d["invalid_rows"]
        assert d["duplicates"] == 1 and good1 in d["duplicate_rows"]
        for e in (good1, good2):
            found = client.get(f"{API}/recipients", params={"search": e}, timeout=30).json()
            assert len(found) == 1
            self.ids.append(found[0]["id"])

    def test_csv_import_preview_and_confirm(self, client):
        e1 = f"{uniq('test.csv1')}@example.com".lower()
        e2 = f"{uniq('test.csv2')}@example.com".lower()
        dept = uniq("TEST_CSVDept")
        content = f"email,department\n{e1},{dept}\n{e2},{dept}\n{e1},{dept}\nbroken@,{dept}\n"
        pre = client.post(f"{API}/recipients/import-preview", json={"content": content}, timeout=30)
        assert pre.status_code == 200, pre.text[:300]
        p = pre.json()
        assert p["summary"] == {"valid": 2, "invalid": 1, "duplicates": 1}, p["summary"]
        assert {x["email"] for x in p["valid"]} == {e1, e2}
        assert p["invalid"][0]["reason"] == "Invalid email"

        conf = client.post(f"{API}/recipients/import-confirm", json={"rows": p["valid"]}, timeout=30)
        assert conf.status_code == 200 and conf.json()["imported"] == 2
        for e in (e1, e2):
            found = client.get(f"{API}/recipients", params={"search": e}, timeout=30).json()
            assert len(found) == 1 and found[0]["department"] == dept
            self.ids.append(found[0]["id"])


class TestSenders:
    def test_sender_crud(self, client):
        seeded = client.get(f"{API}/senders", timeout=30)
        assert seeded.status_code == 200 and isinstance(seeded.json(), list)

        name = uniq("TEST_Sender")
        r = client.post(f"{API}/senders", json={
            "name": name, "email": "qa-sender@example.com", "status": "ACTIVE"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        s = r.json()
        assert s["status"] == "ACTIVE" and s["name"] == name
        sid = s["id"]

        upd = client.put(f"{API}/senders/{sid}", json={
            "name": name + "_E", "email": "qa-sender@example.com", "status": "DISABLED"}, timeout=30)
        assert upd.status_code == 200
        got = [x for x in client.get(f"{API}/senders", timeout=30).json() if x["id"] == sid][0]
        assert got["status"] == "DISABLED" and got["name"] == name + "_E"

        assert client.delete(f"{API}/senders/{sid}", timeout=30).status_code == 200
        assert not [x for x in client.get(f"{API}/senders", timeout=30).json() if x["id"] == sid]


class TestLandingPages:
    def test_landing_crud(self, client):
        name = uniq("TEST_LP")
        r = client.post(f"{API}/landing-pages", json={
            "name": name, "title": "Awareness Check", "message": "Simulated exercise",
            "indicators": "Check sender", "reporting_instructions": "Report it"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        lp = r.json()
        assert lp["title"] == "Awareness Check" and "_id" not in lp
        lid = lp["id"]

        assert client.put(f"{API}/landing-pages/{lid}", json={
            "name": name, "title": "Updated Title", "message": "m",
            "indicators": "i", "reporting_instructions": "r"}, timeout=30).status_code == 200
        got = [x for x in client.get(f"{API}/landing-pages", timeout=30).json() if x["id"] == lid][0]
        assert got["title"] == "Updated Title"

        assert client.delete(f"{API}/landing-pages/{lid}", timeout=30).status_code == 200
        assert not [x for x in client.get(f"{API}/landing-pages", timeout=30).json() if x["id"] == lid]


class TestForms:
    def test_create_form_and_banned_word_rejection(self, client):
        name = uniq("TEST_Form")
        r = client.post(f"{API}/forms", json={"name": name, "fields": [
            {"label": "Full Name", "type": "text", "required": True},
            {"label": "What looked suspicious?", "type": "textarea", "required": False}]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        f = r.json()
        assert len(f["fields"]) == 2 and f["fields"][0]["label"] == "Full Name"
        fid = f["id"]

        bad = client.post(f"{API}/forms", json={"name": uniq("TEST_Bad"), "fields": [
            {"label": "Your password", "type": "text"}]}, timeout=30)
        assert bad.status_code == 400, bad.status_code
        assert "not allowed" in bad.json()["detail"].lower()

        bad2 = client.put(f"{API}/forms/{fid}", json={"name": name, "fields": [
            {"label": "CVV code", "type": "text"}]}, timeout=30)
        assert bad2.status_code == 400

        assert client.delete(f"{API}/forms/{fid}", timeout=30).status_code == 200
