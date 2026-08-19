"""Backend-only smoke test (no frontend).

Usage:
    python scripts/e2e_backend_smoke.py

Requires (all optional but recommended):
    - Backend running on http://localhost:8000
    - Rust rules engine running on http://localhost:3001
    - Member 2 extraction service running on http://localhost:8001
    - AUTH_TOKEN matching the backend's .env (default: dev-token-change-me)
"""

import os
import time
import httpx

BASE = os.getenv("BACKEND_URL", "http://localhost:8000")
TOKEN = os.getenv("AUTH_TOKEN", "dev-token-change-me")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

SAMPLE_OCR = """
Provider: City Medical Group
NPI: 1234567893
Claim Number: GX-2025-883241
Service Date: 07/22/2026
CPT 99284 ER visit $1240.00
Allowed $800.00 Paid $650.00 Patient Resp $150.00
Denial CO-97 Bundled service
Total Billed: $1240.00
"""


def main() -> None:
    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{BASE}/health")
        print("HEALTH", health.status_code, health.text[:300])
        if health.status_code != 200:
            print("FATAL: Backend health check failed — is the backend running?")
            return

        # Direct extraction service check if available
        ext = os.getenv("EXTRACTION_SERVICE_URL", "http://localhost:8001")
        try:
            r = client.post(
                f"{ext}/pipeline",
                json={
                    "document_id": "smoke-1",
                    "raw_ocr_text": SAMPLE_OCR,
                },
            )
            print("EXTRACTION", r.status_code)
            print(r.text[:500])
        except Exception as e:
            print("EXTRACTION unreachable:", e)

        # Full upload test if a sample file exists
        sample_file = os.getenv("SMOKE_SAMPLE_FILE", "")
        if sample_file and os.path.exists(sample_file):
            print(f"\nUPLOAD using {sample_file} ...")
            with open(sample_file, "rb") as f:
                r = client.post(
                    f"{BASE}/api/v1/documents/upload",
                    files={"file": (os.path.basename(sample_file), f, "application/pdf")},
                    headers=HEADERS,
                )
            print("UPLOAD", r.status_code, r.text[:500])
            if r.status_code == 201:
                doc_id = r.json()["id"]
                # Poll status briefly
                for _ in range(15):
                    time.sleep(2)
                    s = client.get(f"{BASE}/api/v1/documents/{doc_id}/status", headers=HEADERS)
                    data = s.json()
                    print("STATUS", data.get("status"))
                    if data.get("status") in ("letter_ready", "error"):
                        break

        print("\nSmoke finished. For full upload test, use authenticated multipart upload to /api/v1/documents/upload")


if __name__ == "__main__":
    main()