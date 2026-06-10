import asyncio
import sys
sys.path.insert(0, 'E:/newjobfinder/jobfinder')

from database.engine import async_session
from sqlalchemy import select
from database.models import Job

async def check_demo_jobs():
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.source == 'demo-data'))
        demo_jobs = result.scalars().all()
        print(f'Demo jobs in pool: {len(demo_jobs)}')
        for job in demo_jobs:
            print(f'  - {job.title[:40]}')
            print(f'    company: {job.company}')
            print(f'    skills_required: {job.skills_required}')
            print(f'    description preview: {(job.description or "")[:100]}...')
            print()

if __name__ == "__main__":
    asyncio.run(check_demo_jobs())