"""
End-to-end smoke test for the Member 3 core.

Usage:
    python scripts/e2e_smoke_test.py

Requires:
    - Backend running on http://localhost:8000
    - Rust rules engine running on http://localhost:3001 (optional but recommended)
    - AUTH_TOKEN matching the backend's .env (default: dev-token-change-me)
"""

import asyncio
import os
import sys
import time

import httpx

BASE_URL = os.environ.get("SMOKE_TEST_BASE_URL", "http://localhost:8000")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "dev-token-change-me")
TIMEOUT = 60  # seconds to wait for letter_ready


def _headers() -> dict:
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


async def main() -> int:
    print("=== Vitta Member 3 Smoke Test ===")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Health check
        print("\n[1] Health check...")
        r = await client.get("/health")
        r.raise_for_status()
        health = r.json()
        print(f"    Status: {health.get('status')}")
        print(f"    Rules engine: {health.get('rules_engine', {}).get('status')}")
        print(f"    Extraction service: {health.get('extraction_service', {}).get('status')}")
        print(f"    LLM enabled: {health.get('llm_enabled')}")
        print(f"    Auth enabled: {health.get('auth_enabled')}")

        # 2. Upload a tiny dummy file (with auth)
        print("\n[2] Uploading test document...")
        files = {
            "file": ("smoke_test.pdf", b"%PDF-1.4 smoke test content", "application/pdf")
        }
        r = await client.post("/api/v1/documents/upload", files=files, headers=_headers())
        r.raise_for_status()
        doc = r.json()
        doc_id = doc["id"]
        print(f"    Document ID: {doc_id}")
        print(f"    Initial status: {doc['status']}")

        # 3. Poll until terminal state
        print("\n[3] Waiting for processing to finish...")
        start = time.time()
        final_status = None
        while time.time() - start < TIMEOUT:
            r = await client.get(f"/api/v1/documents/{doc_id}/status", headers=_headers())
            r.raise_for_status()
            status_data = r.json()
            final_status = status_data["status"]
            print(f"    Current status: {final_status}")
            if final_status in ("letter_ready", "error"):
                break
            await asyncio.sleep(2)

        if final_status != "letter_ready":
            print(f"\nFAILED: Expected letter_ready, got {final_status}")
            if status_data.get("error_message"):
                print(f"    Error: {status_data['error_message']}")
            return 1

        # 4. Fetch full result
        print("\n[4] Fetching full result...")
        r = await client.get(f"/api/v1/documents/{doc_id}", headers=_headers())
        r.raise_for_status()
        full = r.json()
        result = full.get("result")

        if not result:
            print("FAILED: No result object present")
            return 1

        line_items = result.get("line_items") or []
        letter = result.get("letter")
        audit = result.get("audit") or {}

        print(f"    Line items: {len(line_items)}")
        print(f"    Letter status: {letter.get('status') if letter else None}")
        print(f"    Extraction path: {audit.get('extraction_path')}")
        print(f"    Text extraction method: {audit.get('text_extraction', {}).get('method')}")
        print(f"    Rules flags added: {audit.get('rules_engine', {}).get('flags_added')}")

        if not letter or not letter.get("content_markdown"):
            print("FAILED: Letter missing or empty")
            return 1

        # 5. Test letter edit endpoint (with auth)
        print("\n[5] Testing letter edit endpoint...")
        edit_payload = {
            "content_markdown": letter["content_markdown"] + "\n\n<!-- smoke test edit -->"
        }
        r = await client.patch(
            f"/api/v1/documents/{doc_id}/letter",
            json=edit_payload,
            headers=_headers(),
        )
        r.raise_for_status()
        edit_result = r.json()
        print(f"    Letter status after edit: {edit_result.get('letter', {}).get('status')}")
        print(f"    Is fully verified: {edit_result.get('is_fully_verified')}")

        # 6. Verify auth is enforced
        print("\n[6] Verifying auth enforcement...")
        r = await client.get(f"/api/v1/documents/{doc_id}/status")
        if r.status_code == 401:
            print("    Auth correctly rejects unauthenticated requests")
        else:
            print(f"    WARNING: Auth not enforced (got HTTP {r.status_code})")

        print("\n=== SMOKE TEST PASSED ===")
        return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"\nSmoke test crashed: {e}")
        sys.exit(1)