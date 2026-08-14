"""
test_new_api.py - 새 구조(app.main) 엔드포인트 통합 테스트
실행: python test_new_api.py
"""
import urllib.request
import json

BASE = "http://localhost:8000"


def post_json(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read()), r.status


# ─── 1) GET /api/health ─────────────────────────────────────────
with urllib.request.urlopen(f"{BASE}/api/health") as r:
    h = json.loads(r.read())
print(f"[GET  /api/health]       status={h['status']}")

# ─── 2) GET /api/products/{id} ──────────────────────────────────
with urllib.request.urlopen(f"{BASE}/api/products/lv-neverfull-mm") as r:
    p = json.loads(r.read())
print(f"[GET  /api/products/id]  {p['brand']} {p['name']} | score={p['condition_score']} grade={p['condition_grade']}")

# ─── 3) POST /api/fingerprint (multipart) ───────────────────────
import urllib.parse, io
boundary = "----FormBoundary7MA4YWxkTrZu0gW"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="product_id"\r\n\r\n'
    f"lv-neverfull-mm\r\n"
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="user_id"\r\n\r\n'
    f"test-user-001\r\n"
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="image"; filename="test.jpg"\r\n'
    f"Content-Type: image/jpeg\r\n\r\n"
    f"FAKEIMAGEBYTES\r\n"
    f"--{boundary}--\r\n"
).encode("utf-8")

req = urllib.request.Request(
    f"{BASE}/api/fingerprint",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    fp = json.loads(r.read())
print(f"[POST /api/fingerprint]  score={fp['condition_score']} grade={fp['condition_grade']} new={fp['is_new_registration']}")
print(f"                         summary={fp['summary'][:60]}...")

print("\n=== ALL TESTS PASSED ===")
