"""Celery tasks for browser-based job scraping."""
import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# Import celery app at the end to avoid circular import
# The task is registered when this module is imported via celery_app.include


def enqueue_browser_scrape(
    query: str = "",
    location: str = "",
    experience_level: Optional[str] = None,
) -> Optional[str]:
    """Enqueue browser scrape task. Returns task ID or None if broker unavailable."""
    try:
        from workers.celery_app import celery_app
        task = celery_app.send_task(
            "workers.tasks_browser.browser_scrape_task",
            kwargs={"query": query, "location": location, "experience_level": experience_level}
        )
        return task.id if task else None
    except Exception as e:
        logger.warning(f"Could not enqueue browser scrape task: {e}")
        return None


# The actual task implementation - will be registered via celery_app.include
def _run_browser_scrape_impl(
    query: str = "",
    location: str = "",
    experience_level: Optional[str] = None,
):
    """Run browser pool scraping task."""
    async def run_scrape():
        from ingestion.engine import run_browser_pool_source
        results = await run_browser_pool_source(
            query=query or None,
            location=location or None,
            experience_level=experience_level,
        )
        return results
    
    try:
        return asyncio.run(run_scrape())
    except Exception as e:
        logger.error(f"Browser scrape task failed: {e}")
        return {"error": str(e)}


# Register the task with Celery
# This happens at module load time when imported via workers.celery_app
def _register_task():
    from workers.celery_app import celery_app
    celery_app.task(name="workers.tasks_browser.browser_scrape_task")(_run_browser_scrape_impl)


_register_task()