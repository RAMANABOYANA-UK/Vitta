"""
Root conftest for Vitta test suite.
Handles environment setup and test isolation across multiple service packages.
"""

import os
import sys
from pathlib import Path

# Set required environment variables before any app imports
# Use SQLite with async support for testing
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

if not os.environ.get("EXTRACTION_SERVICE_URL"):
    os.environ["EXTRACTION_SERVICE_URL"] = "http://localhost:8001"

if not os.environ.get("RULES_ENGINE_URL"):
    os.environ["RULES_ENGINE_URL"] = "http://localhost:3001"

# Isolate app module imports per test directory
# This prevents data-extraction tests from importing backend's app.models
def pytest_configure(config):
    """Configure pytest to handle multiple 'app' packages properly."""
    # Store original path
    config.original_path = sys.path.copy()


def pytest_collection_modifyitems(config, items):
    """
    Isolate test collection by service to prevent cross-service import collisions.
    
    This prevents data-extraction-service/tests from importing
    medical-bill-backend/app when they both have an 'app' package.
    """
    for item in items:
        test_path = Path(item.fspath)
        
        # Determine which service this test belongs to
        if "medical-bill-backend/tests" in str(test_path):
            item.add_marker("backend")
        elif "data-extraction-service/tests" in str(test_path):
            item.add_marker("extraction")
        elif "bill_rules/tests" in str(test_path):
            item.add_marker("rules")
