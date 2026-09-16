import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from app.core.config import get_settings
from app.core.exceptions import DataIngestionError, ResourceNotFoundError

logger = logging.getLogger(__name__)

# Standard column schema mapping
COLUMN_MAPPINGS = {
    "resp_time_hrs": "response_time_hrs",
    "resol_time_hrs": "resolution_time_hrs",
    "cust_rating": "customer_rating",
}

EXPECTED_COLUMNS = [
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary"
]

VALID_CATEGORIES = {"Billing", "Technical", "General"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_STATUSES = {"Open", "Resolved", "Escalated"}


class DataService:
    """Manages CSV ingestion, schema validation, normalization, and SQLite persistence."""

    def __init__(self, db_path: Optional[Path] = None, csv_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or settings.resolved_database_path
        self.csv_path = csv_path or settings.resolved_csv_path

    def get_connection(self) -> sqlite3.Connection:
        """Create and return an SQLite database connection with row factory and WAL mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn

    def initialize_database(self, force_reload: bool = False) -> int:
        """Initialize database schema and ingest CSV data if table is empty or forced."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time_hrs REAL NOT NULL,
                    resolution_time_hrs REAL,
                    agent_id TEXT NOT NULL,
                    customer_rating INTEGER,
                    issue_summary TEXT NOT NULL
                );
            """)

            # Create high-performance B-tree indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_priority ON support_tickets (priority);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets (status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_category ON support_tickets (category);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_agent_id ON support_tickets (agent_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON support_tickets (created_at);")
            conn.commit()

            cursor.execute("SELECT COUNT(*) FROM support_tickets;")
            count = cursor.fetchone()[0]

            if count > 0 and not force_reload:
                logger.info(f"Database already populated with {count} tickets.")
                return count

        logger.info("Ingesting CSV dataset into SQLite database...")
        return self.ingest_csv()

    def ingest_csv(self) -> int:
        """Parse, validate, normalize, and bulk-insert CSV data into SQLite."""
        if not self.csv_path.exists():
            raise DataIngestionError(f"Dataset CSV file not found at path: {self.csv_path}")

        try:
            df = pd.read_csv(self.csv_path, dtype=str)
        except Exception as e:
            raise DataIngestionError(f"Failed to read CSV file: {str(e)}")

        # Normalize column header names
        df.columns = [c.strip().lower() for c in df.columns]
        df.rename(columns=COLUMN_MAPPINGS, inplace=True)

        # Verify required columns exist
        missing_cols = [col for col in EXPECTED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise DataIngestionError(f"Missing required columns in CSV: {missing_cols}")

        cleaned_records: List[Dict[str, Any]] = []

        for idx, row in df.iterrows():
            ticket_id = str(row["ticket_id"]).strip() if pd.notna(row["ticket_id"]) else None
            if not ticket_id:
                logger.warning(f"Row {idx}: skipping record due to missing ticket_id.")
                continue

            created_at_raw = str(row["created_at"]).strip() if pd.notna(row["created_at"]) else None
            if not created_at_raw:
                logger.warning(f"Row {idx} ({ticket_id}): missing created_at.")
                continue

            # Standardize date format YYYY-MM-DD HH:MM
            try:
                parsed_dt = pd.to_datetime(created_at_raw)
                created_at = parsed_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                logger.warning(f"Row {idx} ({ticket_id}): invalid date format '{created_at_raw}'.")
                continue

            category = str(row["category"]).strip().capitalize() if pd.notna(row["category"]) else "General"
            if category not in VALID_CATEGORIES:
                category = "General"

            priority = str(row["priority"]).strip().capitalize() if pd.notna(row["priority"]) else "Low"
            if priority not in VALID_PRIORITIES:
                priority = "Low"

            status = str(row["status"]).strip().capitalize() if pd.notna(row["status"]) else "Open"
            if status not in VALID_STATUSES:
                status = "Open"

            # Parse response_time_hrs
            try:
                response_time = float(row["response_time_hrs"]) if pd.notna(row["response_time_hrs"]) else 0.0
            except ValueError:
                response_time = 0.0

            # Parse resolution_time_hrs: preserve NULL if missing/unresolved
            resolution_time = None
            if pd.notna(row["resolution_time_hrs"]) and str(row["resolution_time_hrs"]).strip():
                try:
                    resolution_time = float(row["resolution_time_hrs"])
                except ValueError:
                    resolution_time = None

            agent_id = str(row["agent_id"]).strip() if pd.notna(row["agent_id"]) else "UNASSIGNED"

            # Parse customer_rating: preserve NULL if missing/unresolved
            customer_rating = None
            if pd.notna(row["customer_rating"]) and str(row["customer_rating"]).strip():
                try:
                    rating_val = int(float(row["customer_rating"]))
                    if 1 <= rating_val <= 5:
                        customer_rating = rating_val
                except ValueError:
                    customer_rating = None

            issue_summary = str(row["issue_summary"]).strip() if pd.notna(row["issue_summary"]) else ""

            cleaned_records.append({
                "ticket_id": ticket_id,
                "created_at": created_at,
                "category": category,
                "priority": priority,
                "status": status,
                "response_time_hrs": response_time,
                "resolution_time_hrs": resolution_time,
                "agent_id": agent_id,
                "customer_rating": customer_rating,
                "issue_summary": issue_summary
            })

        if not cleaned_records:
            raise DataIngestionError("No valid records found in CSV dataset.")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM support_tickets;")
            cursor.executemany("""
                INSERT INTO support_tickets (
                    ticket_id, created_at, category, priority, status,
                    response_time_hrs, resolution_time_hrs, agent_id,
                    customer_rating, issue_summary
                ) VALUES (
                    :ticket_id, :created_at, :category, :priority, :status,
                    :response_time_hrs, :resolution_time_hrs, :agent_id,
                    :customer_rating, :issue_summary
                );
            """, cleaned_records)
            conn.commit()

        total_inserted = len(cleaned_records)
        logger.info(f"Successfully ingested {total_inserted} records into database.")
        return total_inserted

    def get_total_count(self) -> int:
        """Return total number of tickets in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM support_tickets;")
            return cursor.fetchone()[0]

    def get_all_dataframe(self) -> pd.DataFrame:
        """Return entire dataset as a Pandas DataFrame for statistical calculations."""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM support_tickets;", conn)

    def get_ticket_by_id(self, ticket_id: str) -> Dict[str, Any]:
        """Fetch single ticket by unique ticket_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM support_tickets WHERE ticket_id = ?;", (ticket_id.upper().strip(),))
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundError(f"Ticket '{ticket_id}' not found.")
            return dict(row)

    def get_tickets_count(
        self,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count tickets with optional filtering and search."""
        clauses = []
        params: List[Any] = []

        if category:
            clauses.append("category = ?")
            params.append(category)
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if search:
            clauses.append("(ticket_id LIKE ? OR issue_summary LIKE ?)")
            search_param = f"%{search.strip()}%"
            params.extend([search_param, search_param])

        where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT COUNT(*) FROM support_tickets {where_stmt};"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def get_tickets(
        self,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query tickets with optional filtering, search, and pagination."""
        clauses = []
        params: List[Any] = []

        if category:
            clauses.append("category = ?")
            params.append(category)
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if search:
            clauses.append("(ticket_id LIKE ? OR issue_summary LIKE ?)")
            search_param = f"%{search.strip()}%"
            params.extend([search_param, search_param])

        where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM support_tickets {where_stmt} ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


# Singleton helper instance
data_service = DataService()
