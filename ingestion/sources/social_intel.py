"""Social Intelligence ingestion source - adds jobs from Twitter, Reddit, LinkedIn, GitHub."""
from __future__ import annotations
import os
import logging
from typing import List

from ingestion.base import BaseIngestionSource, JobRecord, status_store

logger = logging.getLogger("ingestion.social_intel")


class SocialIntelSource(BaseIngestionSource):
    """Ingests jobs from social platforms (Twitter, Reddit, LinkedIn, GitHub)."""
    
    name = "social_intel"
    
    def __init__(self, keywords: list[str] = None, location: str = "India"):
        if not keywords:
            # Fetch from user profile in DB
            keywords = self._fetch_keywords_from_db()
        self.keywords = keywords or os.getenv("SCRAPE_QUERY", "").split()
        self.location = location or os.getenv("SCRAPE_LOCATION", "India")

    @staticmethod
    def _fetch_keywords_from_db():
        try:
            import sqlite3, json
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "career_agent.db")
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT desired_roles FROM user_preferences ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            if row and row[0]:
                roles = json.loads(row[0])
                return roles[:3] if roles else []
        except Exception:
            pass
        return []
    
    async def fetch(self) -> List[JobRecord]:
        """Fetch jobs from all social platforms."""
        records = []
        
        try:
            from social_intel import search_twitter_jobs, search_reddit_jobs, search_linkedin_jobs, search_github_jobs
            
            for keyword in self.keywords[:3]:
                try:
                    twitter_jobs = search_twitter_jobs(keyword, limit=5)
                    for job in twitter_jobs:
                        records.append(JobRecord(
                            title=job.title[:500],
                            company=job.company[:500] if job.company else "Unknown",
                            location=job.location[:500] if job.location else "Unknown",
                            description=job.description[:2000] if job.description else "",
                            source="twitter",
                            source_url=job.url,
                            apply_url=job.url,
                        ))
                except Exception as e:
                    logger.warning("Twitter fetch failed for '%s': %s", keyword, e)
                
                try:
                    reddit_jobs = search_reddit_jobs(query=keyword, limit=5)
                    for job in reddit_jobs:
                        records.append(JobRecord(
                            title=job.title[:500],
                            company=job.company[:500] if job.company else "Unknown",
                            location=job.location[:500] if job.location else "Unknown",
                            description=job.description[:2000] if job.description else "",
                            source="reddit",
                            source_url=job.url,
                            apply_url=job.url,
                        ))
                except Exception as e:
                    logger.warning("Reddit fetch failed for '%s': %s", keyword, e)
                
                try:
                    linkedin_jobs = search_linkedin_jobs(keyword, self.location, limit=5)
                    for job in linkedin_jobs:
                        records.append(JobRecord(
                            title=job.title[:500],
                            company=job.company[:500] if job.company else "Unknown",
                            location=job.location[:500] if job.location else "Unknown",
                            description=job.description[:2000] if job.description else "",
                            source="linkedin",
                            source_url=job.url,
                            apply_url=job.url,
                        ))
                except Exception as e:
                    logger.warning("LinkedIn fetch failed for '%s': %s", keyword, e)
            
            try:
                github_jobs = search_github_jobs("hiring developer", limit=5)
                for job in github_jobs:
                    records.append(JobRecord(
                        title=job.title[:500],
                        company=job.company[:500] if job.company else "Unknown",
                        location=job.location[:500] if job.location else "Remote",
                        description=job.description[:2000] if job.description else "",
                        source="github",
                        source_url=job.url,
                        apply_url=job.url,
                    ))
            except Exception as e:
                logger.warning("GitHub fetch failed: %s", e)
            
            status_store.record(
                self.name,
                ok=True,
                jobs_fetched=len(records),
                jobs_new=0,
            )
            
        except Exception as e:
            logger.error("Social Intel source failed: %s", e)
            status_store.record(self.name, ok=False, error=str(e)[:200])
        
        return records
