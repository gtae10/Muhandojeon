"""
test_api.py - 간단한 엔드포인트 통합 테스트
실행: python test_api.py
"""
import urllib.request
import json
import sqlite3
from pathlib import Path

BASE = "http://localhost:8000"

# DB에서 테스트용 ID 추출
conn = sqlite3.connect(Path("luxury_clienteling.db"))
user_id    = conn.execute("SELECT user_id FROM users LIMIT 1").fetchone()[0]
product_id = conn.execute("SELECT product_id FROM products LIMIT 1").fetchone()[0]
conn.close()

print(f"Test user_id   : {user_id}")
print(f"Test product_id: {product_id}")

# ─── 1) GET /api/users/{user_id}/assets ─────────────────────────
url = f"{BASE}/api/users/{user_id}/assets"
with urllib.request.urlopen(url) as r:
    data = json.loads(r.read())

total = data["total"]
print(f"\n[GET  /assets] total={total}")
if data["assets"]:
    a = data["assets"][0]
    print(f"  first: {a['brand']} {a['product_name']} | score={a['condition_score']} grade={a['condition_grade']}")
    wd = a.get("wear_details") or {}
    print(f"  wear : scratches={wd.get('scratches',0)} cracks={wd.get('cracks',0)}")

# ─── 2) POST /api/events/log ─────────────────────────────────────
payload = json.dumps({
    "user_id":      user_id,
    "session_id":   "test-session-001",
    "product_id":   product_id,
    "event_type":   "view",
    "duration_sec": 42.5,
    "device":       "mobile",
}).encode("utf-8")

req = urllib.request.Request(
    f"{BASE}/api/events/log",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    ev = json.loads(r.read())
print(f"\n[POST /events/log] event_id={ev['event_id']}  status={ev['status']}")

# ─── 3) GET /health ─────────────────────────────────────────────
with urllib.request.urlopen(f"{BASE}/health") as r:
    h = json.loads(r.read())
print(f"\n[GET  /health]  status={h['status']}  service={h['service']}")

print("\n=== ALL TESTS PASSED ===")
