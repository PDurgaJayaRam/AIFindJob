import asyncio
from sqlalchemy import select
from database.engine import async_session
from database.models import Job, Resume
from matching.scorer import rank_jobs

async def test():
    async with async_session() as session:
        # Get pool jobs
        result = await session.execute(select(Job).where(Job.user_id == None).limit(30))
        pool = [{
            'id': j.id,
            'title': j.title,
            'company': j.company,
            'location': j.location,
            'description': j.description or '',
            'skills_required': j.skills_required or [],
        } for j in result.scalars().all()]
        
        # Get user resume
        result = await session.execute(select(Resume).limit(1))
        resume = result.scalar_one_or_none()
        
        if resume:
            profile = {
                'skills': resume.skills or [],
                'is_fresher': resume.parsed_data.get('is_fresher', True) if resume.parsed_data else True,
                'target_roles': resume.parsed_data.get('target_roles', []) if resume.parsed_data else [],
            }
            matches = rank_jobs(pool, profile)
            print(f'Pool jobs: {len(pool)}')
            print(f'Matched jobs: {len(matches)}')
            print(f'User skills: {profile["skills"]}')
            print(f'Target roles: {profile["target_roles"]}')
            for m in matches[:5]:
                print(f'  - Score {m["match"]["score"]}%: {m["title"][:50]}')
        else:
            print('No resume found')

if __name__ == '__main__':
    asyncio.run(test())