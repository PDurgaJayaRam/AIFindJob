import asyncio
import sys
sys.path.insert(0, 'E:/newjobfinder/jobfinder')

from matching.scorer import rank_jobs

# User profile from database
profile = {
    "skills": ['Java', 'C#', '.NET Core', 'ASP .NET Core', 'Python', 'C++', 'SQL', 'TensorFlow', 'Entity Framework', 'Redis'],
    "is_fresher": True,
    "target_roles": ['Junior Software Developer', 'Entry-Level Cyber Security Specialist', 'Software Quality Assurance Engineer']
}

# Pool jobs (demo-data + some real jobs)
pool = [
    {"id": 1, "title": "Junior Java Developer", "company": "TCS", "location": "Hyderabad",
     "skills_required": ["Java", "SQL", "Spring"], "description": "Entry level Java developer position. 0-2 years experience required."},
    {"id": 2, "title": "Python Django Developer", "company": "Infosys", "location": "Bangalore", 
     "skills_required": ["Python", "Django", "SQL"], "description": "Python backend developer with Django framework."},
    {"id": 3, "title": "C# .NET Developer - Fresher", "company": "Wipro", "location": "Hyderabad",
     "skills_required": ["C#", ".NET", "SQL Server"], "description": "Fresher C# developer position. Entry level job."},
    {"id": 4, "title": "Software Engineer - Java", "company": "Accenture", "location": "Gurgaon",
     "skills_required": ["Java", "Microservices", "Spring Boot"], "description": "Java software engineer for enterprise applications."},
    {"id": 5, "title": "Junior Python Developer - Fresher", "company": "HCL Technologies", "location": "Noida",
     "skills_required": ["Python", "Flask", "REST API"], "description": "Python internship for freshers. Entry level position."},
    {"id": 6, "title": "Backend Developer - Node.js", "company": "Tech Mahindra", "location": "Pune",
     "skills_required": ["Node.js", "JavaScript", "MongoDB"], "description": "Node.js backend developer with 1-3 years experience."},
]

ranked = rank_jobs(pool, profile)
print(f"Ranked {len(ranked)} jobs:")
for job in ranked[:5]:
    print(f"  Score: {job['match']['score']} - {job['title']}")
    print(f"    Matched skills: {job['match']['matched_skills']}")
    print(f"    Role match: {job['match']['role_match']}")
    print(f"    Fresher friendly: {job['match']['fresher_friendly']}")
    print()