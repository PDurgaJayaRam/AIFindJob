"""Celery background tasks."""
from workers.celery_app import celery_app
from agents.orchestrator.orchestrator import AgentOrchestrator


@celery_app.task
def run_job_pipeline_task(resume_text, keywords, locations, auto_apply=False, match_threshold=75.0, max_jobs=20):
    """Run job pipeline in background."""
    import asyncio
    orch = AgentOrchestrator()
    result = asyncio.run(orch.run_job_pipeline(
        resume_text=resume_text,
        keywords=keywords,
        locations=locations,
        auto_apply=auto_apply,
        match_threshold=match_threshold,
        max_jobs=max_jobs,
    ))
    return {
        "jobs_discovered": result.jobs_discovered,
        "jobs_matched": result.jobs_matched,
        "applications_submitted": result.applications_submitted,
        "errors": result.errors,
    }


@celery_app.task
def continuous_scrape_task():
    """Continuous background scraping - runs every 30 minutes via beat schedule.
    
    Fetches jobs for all active users using their saved preferences.
    Jobs are saved to database and available on the dashboard.
    """
    import asyncio
    import logging
    from database.engine import async_session
    from database.models import User, UserPreference, Resume
    from sqlalchemy import select
    from agents.dual_model_orchestrator import DualModelOrchestrator
    
    logger = logging.getLogger(__name__)
    logger.info("Starting continuous scrape task...")
    
    async def scrape_for_all_users():
        async with async_session() as session:
            # Get all active users
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()
            
            logger.info(f"Found {len(users)} active users to scrape for")
            
            for user in users:
                try:
                    # Get user preferences
                    pref_result = await session.execute(
                        select(UserPreference).where(UserPreference.user_id == user.id)
                    )
                    prefs = pref_result.scalar_one_or_none()
                    
                    # Get resume
                    resume_result = await session.execute(
                        select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()).limit(1)
                    )
                    resume = resume_result.scalar_one_or_none()
                    
                    if not resume:
                        logger.warning(f"No resume for user {user.id}, skipping")
                        continue
                    
                    # Build search request
                    keywords = prefs.desired_roles if prefs and prefs.desired_roles else ["Python Developer"]
                    locations = prefs.desired_locations if prefs and prefs.desired_locations else ["Hyderabad"]
                    skills = prefs.skills if prefs and prefs.skills else (resume.skills or [])
                    
                    # Use DualModelOrchestrator to search and save
                    orch = DualModelOrchestrator()
                    result = await orch.run_search(
                        user_request=f"Find {', '.join(keywords)} jobs in {', '.join(locations)}",
                        context={
                            "user_id": user.id,
                            "resume_text": resume.text_content or "",
                            "skills": skills,
                            "keywords": keywords,
                            "locations": locations,
                            "is_fresher": (resume.experience_years or 0) == 0,
                            "auto_apply": prefs.auto_apply_enabled if prefs else False,
                        }
                    )
                    
                    jobs_found = len(result.get("jobs", []))
                    logger.info(f"User {user.id}: Found {jobs_found} jobs")
                    
                except Exception as e:
                    logger.error(f"Error scraping for user {user.id}: {e}")
                    continue
    
    try:
        asyncio.run(scrape_for_all_users())
        logger.info("Continuous scrape task completed successfully")
    except Exception as e:
        logger.error(f"Continuous scrape task failed: {e}")
        raise
