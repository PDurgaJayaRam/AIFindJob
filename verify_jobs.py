import requests
import json

r = requests.get('http://localhost:8000/ingestion/jobs?limit=10')
data = r.json()
jobs = data.get('jobs', [])
demo = [j for j in jobs if j.get('source') == 'demo-data']
print(f'Demo jobs found: {len(demo)}')
for j in demo[:6]:
    print(f'  {j.get("title")[:50]} - {j.get("company")}')