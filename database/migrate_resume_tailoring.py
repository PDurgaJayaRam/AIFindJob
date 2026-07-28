"""Migration: Add resume tailoring columns to resumes and custom_resumes tables."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "career_agent.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}, skipping migration")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check resumes table columns
        cursor.execute("PRAGMA table_info(resumes)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current resumes columns: {columns}")
        
        # Add missing columns to resumes table
        if "parsed_sections" not in columns:
            cursor.execute("ALTER TABLE resumes ADD COLUMN parsed_sections JSON DEFAULT '{}' ")
            print("Added parsed_sections column to resumes")
        
        if "format_preserved" not in columns:
            cursor.execute("ALTER TABLE resumes ADD COLUMN format_preserved JSON DEFAULT '{}' ")
            print("Added format_preserved column to resumes")
        
        # Check if custom_resumes table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_resumes'")
        if not cursor.fetchone():
            # Create custom_resumes table
            cursor.execute("""
                CREATE TABLE custom_resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    user_id INTEGER,
                    original_resume_text TEXT,
                    original_resume_sections JSON DEFAULT '{}',
                    resume_text TEXT,
                    resume_pdf_path VARCHAR(500),
                    resume_docx_path VARCHAR(500),
                    match_score FLOAT DEFAULT 0.0,
                    matching_skills JSON DEFAULT '[]',
                    missing_skills JSON DEFAULT '[]',
                    recommended_skills JSON DEFAULT '[]',
                    optimization_suggestions JSON DEFAULT '[]',
                    job_analysis JSON DEFAULT '{}',
                    ats_optimized BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            print("Created custom_resumes table")
        else:
            # Add missing columns to existing custom_resumes table
            cursor.execute("PRAGMA table_info(custom_resumes)")
            custom_columns = [row[1] for row in cursor.fetchall()]
            print(f"Current custom_resumes columns: {custom_columns}")
            
            columns_to_add = [
                ("original_resume_text", "TEXT"),
                ("original_resume_sections", "JSON DEFAULT '{}'"),
                ("match_score", "FLOAT DEFAULT 0.0"),
                ("matching_skills", "JSON DEFAULT '[]'"),
                ("missing_skills", "JSON DEFAULT '[]'"),
                ("recommended_skills", "JSON DEFAULT '[]'"),
                ("optimization_suggestions", "JSON DEFAULT '[]'"),
                ("job_analysis", "JSON DEFAULT '{}'")
            ]
            
            for col_name, col_type in columns_to_add:
                if col_name not in custom_columns:
                    cursor.execute(f"ALTER TABLE custom_resumes ADD COLUMN {col_name} {col_type}")
                    print(f"Added {col_name} column to custom_resumes")
        
        conn.commit()
        print("Migration complete")
    except Exception as e:
        print(f"Migration error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()