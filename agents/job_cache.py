"""Job Caching System - Prevent duplicate scraping and improve performance.

Features:
- Cache jobs by keyword + location + portal
- TTL-based expiration (24 hours default)
- SQLite-backed persistence
- Smart deduplication across portals
"""
import time
import json
import hashlib
import sqlite3
from typing import List, Dict, Optional, Set
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Cache TTL: 24 hours
DEFAULT_TTL = 86400

class JobCache:
    """SQLite-backed job cache for deduplication and performance."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "job_cache.db")
        
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL,
                    portal TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    location TEXT NOT NULL,
                    jobs_json TEXT NOT NULL,
                    job_count INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(cache_key, portal)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_hash TEXT NOT NULL UNIQUE,
                    source_url TEXT,
                    title TEXT,
                    company TEXT,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_key 
                ON job_cache(cache_key, portal)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_seen_hash 
                ON seen_jobs(job_hash)
            """)
            
            conn.commit()
    
    def _make_cache_key(self, keyword: str, location: str) -> str:
        """Create a cache key from keyword and location."""
        raw = f"{keyword.lower().strip()}|{location.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()
    
    def _make_job_hash(self, job: Dict) -> str:
        """Create a unique hash for a job to detect duplicates."""
        # Use title + company + source_url as unique identifier
        title = (job.get("title") or "").lower().strip()
        company = (job.get("company") or "").lower().strip()
        source_url = (job.get("source_url") or job.get("apply_url") or "").strip()
        
        # If we have a URL, use that as primary identifier
        if source_url:
            raw = source_url
        else:
            # Fallback to title + company
            raw = f"{title}|{company}"
        
        return hashlib.md5(raw.encode()).hexdigest()
    
    def get_cached_jobs(self, keyword: str, location: str, portal: str) -> Optional[List[Dict]]:
        """Get cached jobs for a search query. Returns None if cache miss or expired."""
        cache_key = self._make_cache_key(keyword, location)
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT jobs_json, expires_at 
                FROM job_cache 
                WHERE cache_key = ? AND portal = ?
            """, (cache_key, portal))
            
            row = cursor.fetchone()
            if row is None:
                return None
            
            jobs_json, expires_at = row
            
            # Check if expired
            if now > expires_at:
                # Delete expired entry
                conn.execute("""
                    DELETE FROM job_cache 
                    WHERE cache_key = ? AND portal = ?
                """, (cache_key, portal))
                conn.commit()
                return None
            
            try:
                jobs = json.loads(jobs_json)
                logger.info(f"Cache HIT for '{keyword}' in {location} on {portal}: {len(jobs)} jobs")
                return jobs
            except json.JSONDecodeError:
                return None
    
    def cache_jobs(self, keyword: str, location: str, portal: str, jobs: List[Dict], ttl: int = DEFAULT_TTL):
        """Cache jobs for a search query."""
        if not jobs:
            return
        
        cache_key = self._make_cache_key(keyword, location)
        now = time.time()
        expires_at = now + ttl
        
        with sqlite3.connect(self.db_path) as conn:
            # Upsert: delete old entry if exists, then insert
            conn.execute("""
                DELETE FROM job_cache 
                WHERE cache_key = ? AND portal = ?
            """, (cache_key, portal))
            
            conn.execute("""
                INSERT INTO job_cache (cache_key, portal, keyword, location, jobs_json, job_count, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key, portal, keyword, location,
                json.dumps(jobs), len(jobs), now, expires_at
            ))
            
            conn.commit()
            logger.info(f"Cached {len(jobs)} jobs for '{keyword}' in {location} on {portal}")
    
    def is_job_seen(self, job: Dict) -> bool:
        """Check if a job has been seen before (cross-portal deduplication)."""
        job_hash = self._make_job_hash(job)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id FROM seen_jobs WHERE job_hash = ?
            """, (job_hash,))
            
            return cursor.fetchone() is not None
    
    def mark_job_seen(self, job: Dict):
        """Mark a job as seen to prevent duplicate processing."""
        job_hash = self._make_job_hash(job)
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            # Upsert: update last_seen_at if exists, otherwise insert
            conn.execute("""
                INSERT INTO seen_jobs (job_hash, source_url, title, company, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_hash) DO UPDATE SET last_seen_at = ?
            """, (
                job_hash,
                job.get("source_url") or job.get("apply_url"),
                job.get("title"),
                job.get("company"),
                now, now, now
            ))
            
            conn.commit()
    
    def deduplicate_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """Remove duplicate jobs from a list and mark them as seen."""
        seen_hashes: Set[str] = set()
        unique_jobs = []
        
        for job in jobs:
            job_hash = self._make_job_hash(job)
            
            # Skip if we've seen this hash in this batch
            if job_hash in seen_hashes:
                continue
            
            # Skip if we've seen this job before (cross-session)
            if self.is_job_seen(job):
                continue
            
            # Mark as seen
            seen_hashes.add(job_hash)
            self.mark_job_seen(job)
            unique_jobs.append(job)
        
        removed = len(jobs) - len(unique_jobs)
        if removed > 0:
            logger.info(f"Deduplicated: {len(jobs)} → {len(unique_jobs)} jobs ({removed} duplicates removed)")
        
        return unique_jobs
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total cached queries
            cursor = conn.execute("SELECT COUNT(*) FROM job_cache")
            total_queries = cursor.fetchone()[0]
            
            # Total cached jobs
            cursor = conn.execute("SELECT SUM(job_count) FROM job_cache")
            total_jobs = cursor.fetchone()[0] or 0
            
            # Total seen jobs
            cursor = conn.execute("SELECT COUNT(*) FROM seen_jobs")
            total_seen = cursor.fetchone()[0]
            
            # Portal breakdown
            cursor = conn.execute("""
                SELECT portal, COUNT(*) as queries, SUM(job_count) as jobs
                FROM job_cache
                GROUP BY portal
            """)
            portal_stats = {
                row[0]: {"queries": row[1], "jobs": row[2] or 0}
                for row in cursor.fetchall()
            }
            
            return {
                "total_cached_queries": total_queries,
                "total_cached_jobs": total_jobs,
                "total_seen_jobs": total_seen,
                "by_portal": portal_stats
            }
    
    def clear_expired(self):
        """Remove all expired cache entries."""
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM job_cache WHERE expires_at < ?
            """, (now,))
            
            deleted = cursor.rowcount
            conn.commit()
            
            if deleted > 0:
                logger.info(f"Cleared {deleted} expired cache entries")
            
            return deleted
    
    def clear_all(self):
        """Clear all cache data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM job_cache")
            conn.execute("DELETE FROM seen_jobs")
            conn.commit()
            logger.info("Cleared all cache data")


# Global cache instance
_job_cache: Optional[JobCache] = None


def get_job_cache() -> JobCache:
    """Get the global job cache instance."""
    global _job_cache
    if _job_cache is None:
        _job_cache = JobCache()
    return _job_cache
