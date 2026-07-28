"""Verify jobs in the database - check for real sources and URLs."""
import requests
import json

# Check database directly
import sqlite3
conn = sqlite3.connect('data/career_agent.db')
c = conn.cursor()

print("=== Job Pool Verification ===\n")

# Check sources
c.execute("SELECT source, COUNT(*) FROM jobs GROUP BY source ORDER BY COUNT(*) DESC")
print("Jobs by source:")
for src, cnt in c.fetchall():
    print(f"  {src}: {cnt} jobs")

# Check for fake/demo jobs
c.execute("SELECT COUNT(*) FROM jobs WHERE source = 'demo-data' OR source_url LIKE '%demo%' OR source_url LIKE '%fake%'")
fake_count = c.fetchone()[0]
print(f"\nFake/demo jobs found: {fake_count}")

# Check jobs with missing URLs
c.execute("SELECT COUNT(*) FROM jobs WHERE source_url IS NULL OR source_url = ''")
no_url = c.fetchone()[0]
print(f"Jobs with missing URLs: {no_url}")

conn.close()

print("\n=== Scraping Status ===")
try:
    r = requests.get('http://localhost:8000/ingestion/status', timeout=2)
    if r.ok:
        print(f"Ingestion status: {r.json()}")
    else:
        print("Backend not running or error")
except Exception as e:
    print(f"Could not connect to backend: {e}")