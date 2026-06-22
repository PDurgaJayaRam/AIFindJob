"""Export jobs to Google Sheets format."""
import sqlite3
import csv
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "career_agent.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "exports")


def export_jobs_to_csv():
    """Export all jobs to a CSV file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id, title, company, location, source, description,
            skills_required, salary, experience_required, apply_url,
            source_url, remote, fresher_friendly, match_score,
            posted_date, created_at
        FROM jobs 
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    filename = f"jobs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    
    conn.close()
    return filepath, len(rows)


def export_jobs_to_html():
    """Export all jobs to an HTML table (Google Sheets style)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id, title, company, location, source, 
            substr(description, 1, 200) as description_preview,
            skills_required, salary, experience_required, apply_url,
            remote, fresher_friendly, match_score, created_at
        FROM jobs 
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>AIFindJob - Job Database</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f8f9fa; }
        .header { background: #1a73e8; color: white; padding: 20px; }
        .header h1 { font-size: 24px; }
        .header p { opacity: 0.9; margin-top: 5px; }
        .stats { display: flex; gap: 20px; padding: 15px 20px; background: white; border-bottom: 1px solid #e0e0e0; }
        .stat { text-align: center; }
        .stat-num { font-size: 24px; font-weight: bold; color: #1a73e8; }
        .stat-label { font-size: 12px; color: #666; }
        .table-container { overflow-x: auto; padding: 20px; }
        table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        th { background: #f1f3f4; padding: 12px 8px; text-align: left; font-weight: 500; border-bottom: 2px solid #e0e0e0; position: sticky; top: 0; }
        td { padding: 10px 8px; border-bottom: 1px solid #e0e0e0; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        tr:hover { background: #f8f9fa; }
        .source-badge { padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
        .source-remoteok { background: #e8f5e9; color: #2e7d32; }
        .source-linkedin { background: #e3f2fd; color: #1565c0; }
        .source-indeed { background: #fff3e0; color: #e65100; }
        .source-naukri { background: #fce4ec; color: #c62828; }
        .source-arbeitnow { background: #f3e5f5; color: #6a1b9a; }
        .source-github { background: #e8eaf6; color: #283593; }
        .source-default { background: #f5f5f5; color: #616161; }
        .link { color: #1a73e8; text-decoration: none; }
        .link:hover { text-decoration: underline; }
        .skills { display: flex; flex-wrap: wrap; gap: 4px; }
        .skill-tag { background: #e8eaf6; color: #3949ab; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
        .filter-bar { padding: 15px 20px; background: white; border-bottom: 1px solid #e0e0e0; display: flex; gap: 10px; }
        .filter-bar input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; width: 300px; }
        .filter-bar select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>AIFindJob - Job Database</h1>
        <p>All scraped jobs from multiple sources</p>
    </div>
    <div class="stats">
        <div class="stat"><div class="stat-num">""" + str(len(rows)) + """</div><div class="stat-label">Total Jobs</div></div>
"""
    
    cursor.execute("SELECT source, COUNT(*) FROM jobs GROUP BY source ORDER BY COUNT(*) DESC")
    for source, count in cursor.fetchall():
        html += f'<div class="stat"><div class="stat-num">{count}</div><div class="stat-label">{source}</div></div>'
    
    html += """    </div>
    <div class="filter-bar">
        <input type="text" id="search" placeholder="Search jobs..." onkeyup="filterTable()">
        <select id="sourceFilter" onchange="filterTable()">
            <option value="">All Sources</option>
"""
    
    cursor.execute("SELECT DISTINCT source FROM jobs ORDER BY source")
    for (source,) in cursor.fetchall():
        html += f'            <option value="{source}">{source}</option>\n'
    
    html += """        </select>
    </div>
    <div class="table-container">
        <table id="jobsTable">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Company</th>
                    <th>Location</th>
                    <th>Source</th>
                    <th>Description</th>
                    <th>Skills</th>
                    <th>Salary</th>
                    <th>Experience</th>
                    <th>Remote</th>
                    <th>Fresher</th>
                    <th>Match</th>
                    <th>Posted</th>
                    <th>Link</th>
                </tr>
            </thead>
            <tbody>
"""
    
    for row in rows:
        job_id, title, company, location, source, desc, skills, salary, exp, apply_url, remote, fresher, match, created = row
        
        source_class = f"source-{source}" if source in ['remoteok', 'linkedin', 'indeed', 'naukri', 'arbeitnow', 'github'] else "source-default"
        
        skills_html = ""
        if skills:
            try:
                import json
                skills_list = json.loads(skills) if isinstance(skills, str) else skills
                skills_html = '<div class="skills">' + ''.join(f'<span class="skill-tag">{s}</span>' for s in skills_list[:5]) + '</div>'
            except:
                skills_html = str(skills)[:50]
        
        html += f"""                <tr>
                    <td>{job_id}</td>
                    <td title="{title or ''}">{(title or '')[:60]}</td>
                    <td>{(company or '')[:40]}</td>
                    <td>{(location or '')[:30]}</td>
                    <td><span class="source-badge {source_class}">{source or ''}</span></td>
                    <td title="{desc or ''}">{(desc or '')[:80]}</td>
                    <td>{skills_html}</td>
                    <td>{(salary or '')[:20]}</td>
                    <td>{(exp or '')[:20]}</td>
                    <td>{'Yes' if remote else 'No'}</td>
                    <td>{'Yes' if fresher else 'No'}</td>
                    <td>{match or ''}</td>
                    <td>{(created or '')[:10]}</td>
                    <td>{'<a class="link" href="' + (apply_url or '#') + '" target="_blank">Apply</a>' if apply_url else ''}</td>
                </tr>
"""
    
    html += """            </tbody>
        </table>
    </div>
    <script>
        function filterTable() {
            const search = document.getElementById('search').value.toLowerCase();
            const source = document.getElementById('sourceFilter').value.toLowerCase();
            const rows = document.querySelectorAll('#jobsTable tbody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const matchesSearch = !search || text.includes(search);
                const matchesSource = !source || row.querySelector('.source-badge')?.textContent.toLowerCase() === source;
                row.style.display = (matchesSearch && matchesSource) ? '' : 'none';
            });
        }
    </script>
</body>
</html>"""
    
    filename = f"jobs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    conn.close()
    return filepath, len(rows)


if __name__ == "__main__":
    csv_path, csv_count = export_jobs_to_csv()
    html_path, html_count = export_jobs_to_html()
    
    print(f"CSV exported: {csv_path} ({csv_count} jobs)")
    print(f"HTML exported: {html_path} ({html_count} jobs)")
    print(f"\nOpen the HTML file in your browser to view jobs in Google Sheets style.")
