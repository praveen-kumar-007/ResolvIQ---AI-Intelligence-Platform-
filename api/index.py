import os
import shutil
from pathlib import Path
from app.main import app

# Ensure SQLite database is accessible in Vercel's ephemeral /tmp directory
if os.environ.get("VERCEL"):
    os.environ["DATABASE_PATH"] = "/tmp/support_tickets.db"
    base_dir = Path(__file__).parent.parent
    db_src = base_dir / "data" / "support_tickets.db"
    db_dst = Path("/tmp/support_tickets.db")
    if db_src.exists() and not db_dst.exists():
        shutil.copy(db_src, db_dst)
