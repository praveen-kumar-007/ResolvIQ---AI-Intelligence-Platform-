"""
Vercel Serverless Function Entrypoint
Initializes ephemeral storage in /tmp, configures paths, and exposes the ASGI FastAPI app.
"""
import os
import shutil
import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' package is discoverable
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Configure environment for Vercel Serverless execution
os.environ["ENVIRONMENT"] = "production"

# Vercel serverless has a read-only filesystem except /tmp
if os.environ.get("VERCEL") or sys.platform != "win32":
    tmp_db = Path("/tmp/support_tickets.db")
    os.environ["DATABASE_PATH"] = str(tmp_db)

    # Seed /tmp database from source if available
    src_db = root_dir / "data" / "support_tickets.db"
    if src_db.exists() and not tmp_db.exists():
        try:
            shutil.copy(src_db, tmp_db)
        except Exception:
            pass

# Import the FastAPI application
from app.main import app  # noqa: E402
from app.services.data_service import data_service  # noqa: E402

# Ensure SQLite database is fully initialized on cold start
try:
    data_service.initialize_database()
except Exception:
    pass
