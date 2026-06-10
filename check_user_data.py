import asyncio
import sys
sys.path.insert(0, 'E:/newjobfinder/jobfinder')

from database.engine import async_session
from sqlalchemy import select
from database.models import Job, Resume, User

async def check_user_data():
    async with async_session() as session:
        # Check user 1 (the one in the logs)
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalar_one_or_none()
        if user:
            print(f'User 1: {user.email}')
        else:
            print('User 1 not found, checking for any users...')
            result = await session.execute(select(User))
            users = result.scalars().all()
            print(f'Found {len(users)} users')
            for u in users[:3]:
                print(f'  - {u.email} (id={u.id})')
        
        # Check resumes for user 1
        if user:
            result = await session.execute(select(Resume).where(Resume.user_id == user.id))
            resumes = result.scalars().all()
            print(f'\nResumes for user 1: {len(resumes)}')
            for r in resumes[:3]:
                print(f'  - skills: {r.skills}')
                print(f'  - target_roles: {r.parsed_data.get("target_roles") if r.parsed_data else []}')
        
        # Check demo jobs
        result = await session.execute(select(Job).where(Job.source == 'demo-data'))
        demo_jobs = result.scalars().all()
        print(f'\nDemo jobs in pool: {len(demo_jobs)}')

if __name__ == "__main__":
    asyncio.run(check_user_data())