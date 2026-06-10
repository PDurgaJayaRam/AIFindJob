import asyncio
from sqlalchemy import select
from database.engine import async_session
from database.models import User, Resume

async def check():
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f'User: {u.email} (id={u.id})')
            result2 = await session.execute(select(Resume).where(Resume.user_id == u.id))
            resume = result2.scalar_one_or_none()
            if resume:
                print(f'  Resume: {resume.filename}')
                print(f'  Skills: {resume.skills}')
                print(f'  Target roles: {resume.parsed_data.get("target_roles", [])}')
            else:
                print('  NO RESUME')

if __name__ == '__main__':
    asyncio.run(check())