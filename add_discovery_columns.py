"""Migration: Add discovery columns to recruiters table."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "career_agent.db")

COLUMNS_TO_ADD = [
    ("photo_url", "TEXT"),
    ("location", "VARCHAR(500)"),
    ("relevance", "VARCHAR(20)"),
    ("skills", "TEXT"),  # JSON stored as TEXT in SQLite
    ("contact_type", "VARCHAR(50)"),
    ("is_recruiter", "BOOLEAN DEFAULT 0"),
    ("is_hiring_manager", "BOOLEAN DEFAULT 0"),
    ("verified", "BOOLEAN DEFAULT 0"),
    ("outreach_linkedin", "TEXT"),
    ("outreach_email_subject", "TEXT"),
    ("outreach_email_body", "TEXT"),
]


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}, skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(recruiters)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    added = 0
    for col_name, col_type in COLUMNS_TO_ADD:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE recruiters ADD COLUMN {col_name} {col_type}")
                added += 1
                print(f"  Added '{col_name}' ({col_type})")
            except sqlite3.OperationalError as e:
                print(f"  Failed to add '{col_name}': {e}")

    if added > 0:
        conn.commit()
        print(f"\nMigration complete: added {added} column(s) to recruiters table.")
    else:
        print("\nAll columns already exist. No migration needed.")

    conn.close()


if __name__ == "__main__":
    migrate()
