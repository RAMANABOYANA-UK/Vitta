"""
End-to-end smoke test for the Member 3 core.

Usage:
    python scripts/e2e_smoke_test.py

Requires:
    - Backend running on http://localhost:8000
    - Rust rules engine running on http://localhost:3001 (optional but recommended)
"""

import asyncio
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT = 60  # seconds to wait for letter_ready


async def main() -> int:
    print("=== Vitta Member 3 Smoke Test ===")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Health check
        print("\n[1] Health check...")
        r = await client.get("/health")
        r.raise_for_status()
        health = r.json()
        print(f"    Status: {health.get('status')}")
        print(f"    Rules engine: {health.get('dependencies', {}).get('rules_engine', {}).get('status')}")

        # 2. Upload a tiny dummy file
        print("\n[2] Uploading test document...")
        files = {
            "file": ("smoke_test.pdf", b"%PDF-1.4 smoke test content", "application/pdf")
        }
        r = await client.post("/api/v1/documents/upload", files=files)
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
            r = await client.get(f"/api/v1/documents/{doc_id}/status")
            r.raise_for_status()
            status_data = r.json()
            final_status = status_data["status"]
            print(f"    Current status: {final_status}")
            if final_status in ("letter_ready", "error"):
                break
            await asyncio.sleep(2)

        if final_status != "letter_ready":
            print(f"\nFAILED: Expected letter_ready, got {final_status}")
            return 1

        # 4. Fetch full result
        print("\n[4] Fetching full result...")
        r = await client.get(f"/api/v1/documents/{doc_id}")
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
        print(f"    Rules flags added: {audit.get('rules_engine', {}).get('flags_added')}")

        if not letter or not letter.get("content_markdown"):
            print("FAILED: Letter missing or empty")
            return 1

        print("\n=== SMOKE TEST PASSED ===")
        return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"\nSmoke test crashed: {e}")
        sys.exit(1)