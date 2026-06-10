import asyncio
import sys
sys.path.insert(0, 'E:/newjobfinder/jobfinder')

from database.engine import async_session
from sqlalchemy import select
from database.models import Job

async def check_jobs():
    async with async_session() as session:
        # Count total jobs
        result = await session.execute(select(Job))
        all_jobs = result.scalars().all()
        print(f'Total jobs in database: {len(all_jobs)}')
        
        # Show sources
        result = await session.execute(select(Job.source).distinct())
        sources = [s[0] for s in result.fetchall()]
        print(f'Sources: {sources}')
        
        # Show sample jobs
        result = await session.execute(select(Job).limit(10))
        for job in result.scalars().all():
            skills = job.skills_required[:3] if job.skills_required else []
            print(f'  - {job.title[:50] if job.title else "No title"}... ({job.source}) - skills: {skills}')

if __name__ == "__main__":
    asyncio.run(check_jobs())