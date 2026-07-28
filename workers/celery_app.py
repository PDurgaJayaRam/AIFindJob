"""Celery app for background job processing."""
import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "combo_ai_agent",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks", "workers.tasks_browser"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Beat schedule for continuous job scraping (runs every 2 hours)
celery_app.conf.beat_schedule = {
    "continuous-job-scrape": {
        "task": "workers.tasks.continuous_scrape_task",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "args": (),
    },
    "browser-pool-scrape": {
        "task": "workers.tasks_browser.browser_scrape_task",
        "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours
        "args": (),
    },
}
