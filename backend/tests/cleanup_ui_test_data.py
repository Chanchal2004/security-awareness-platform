"""One-off cleanup for recipients created by the UI (Playwright) test run."""
import re
from pathlib import Path

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
creds_text = Path("/app/memory/test_credentials.md").read_text()
email = re.search(r"Email:\s*`([^`]+)`", creds_text).group(1)
password = re.search(r"Password:\s*`([^`]+)`", creds_text).group(1)

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
r.raise_for_status()
recips = s.get(f"{API}/recipients", timeout=30).json()
removed = []
for rec in recips:
    if rec["email"].startswith(("test_qa", "test_csv", "test_put")):
        s.delete(f"{API}/recipients/{rec['id']}", timeout=30)
        removed.append(rec["email"])
print("removed:", removed)
