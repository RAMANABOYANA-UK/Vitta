"""Quick import verification for all backend modules."""

import sys
from pathlib import Path

# Ensure the project root is on the path when run from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

modules = [
    "app.main",
    "app.config",
    "app.database",
    "app.models",
    "app.schemas",
    "app.services.document_text",
    "app.services.extraction_client",
    "app.services.letter_generator",
    "app.services.letter_verifier",
    "app.services.mock_data",
    "app.services.pipeline",
    "app.services.rules_engine",
    "app.services.storage",
    "app.core.security",
    "app.api.routes.documents",
    "app.api.routes.health",
]

failed = []
for mod in modules:
    try:
        __import__(mod)
        print(f"OK: {mod}")
    except Exception as e:
        failed.append((mod, str(e)))
        print(f"FAIL: {mod}: {e}")

if failed:
    print(f"\n{len(failed)} module(s) failed to import")
    sys.exit(1)

print("\nALL MODULES IMPORT OK")