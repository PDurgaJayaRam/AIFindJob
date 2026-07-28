import sqlite3, json
from resume_tailor.resume_parser import parse_resume_sections

conn = sqlite3.connect('data/career_agent.db')
cursor = conn.cursor()

cursor.execute("SELECT id, text_content FROM resumes")
rows = cursor.fetchall()

for resume_id, text_content in rows:
    if not text_content:
        continue
    
    sections = parse_resume_sections(text_content)
    
    cursor.execute(
        "UPDATE resumes SET parsed_sections = ? WHERE id = ?",
        (json.dumps(sections), resume_id)
    )
    print(f"Updated resume {resume_id}: education={len(sections.get('education', []))}, "
          f"skills={len(sections.get('skills', []))}, "
          f"projects={len(sections.get('projects', []))}, "
          f"certifications={len(sections.get('certifications', []))}")

conn.commit()
conn.close()
print("\nDone! All resumes re-parsed.")
