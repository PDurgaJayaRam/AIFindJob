"""Social Intelligence API Router - Endpoints for social job monitoring."""
from __future__ import annotations
import logging
from typing import Callable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

logger = logging.getLogger("social_intel.router")


class JobSearchRequest(BaseModel):
    query: str
    location: str = "India"
    limit: int = 20


class CompanyResearchRequest(BaseModel):
    company_name: str


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/social", tags=["social-intelligence"])
    
    @router.post("/search-jobs")
    async def search_social_jobs(request: JobSearchRequest, user=Depends(get_current_user)):
        """Search multiple social platforms for job opportunities."""
        from social_intel import monitor_job_market
        
        results = monitor_job_market(keywords=[request.query], location=request.location)
        
        return {
            "query": request.query,
            "location": request.location,
            "total_found": results["total_jobs"],
            "by_source": results["by_source"],
            "jobs": results["jobs"][:request.limit],
        }
    
    @router.post("/search-twitter")
    async def search_twitter(request: JobSearchRequest, user=Depends(get_current_user)):
        """Search Twitter/X for job postings (via Google search)."""
        from social_intel import search_twitter_jobs
        
        jobs = search_twitter_jobs(request.query, limit=request.limit)
        
        return {
            "source": "twitter",
            "total_found": len(jobs),
            "jobs": [{"title": j.title, "company": j.company, "location": j.location, "url": j.url, "description": j.description[:200]} for j in jobs],
        }
    
    @router.post("/search-reddit")
    async def search_reddit(request: JobSearchRequest, subreddit: str = Query(default="jobs"), user=Depends(get_current_user)):
        """Search Reddit for job postings (via RSS feeds)."""
        from social_intel import search_reddit_jobs
        
        jobs = search_reddit_jobs(subreddit=subreddit, query=request.query, limit=request.limit)
        
        return {
            "source": "reddit",
            "subreddit": subreddit,
            "total_found": len(jobs),
            "jobs": [{"title": j.title, "company": j.company, "location": j.location, "url": j.url, "description": j.description[:200]} for j in jobs],
        }
    
    @router.post("/search-linkedin")
    async def search_linkedin(request: JobSearchRequest, user=Depends(get_current_user)):
        """Search LinkedIn for job postings (via Jina Reader)."""
        from social_intel import search_linkedin_jobs
        
        jobs = search_linkedin_jobs(request.query, request.location, limit=request.limit)
        
        return {
            "source": "linkedin",
            "total_found": len(jobs),
            "jobs": [{"title": j.title, "company": j.company, "location": j.location, "url": j.url, "description": j.description[:200]} for j in jobs],
        }
    
    @router.post("/research-company")
    async def research_company(request: CompanyResearchRequest, user=Depends(get_current_user)):
        """Research a company using GitHub."""
        from social_intel import get_company_insight
        
        insight = get_company_insight(request.company_name)
        
        return {
            "company": insight["name"],
            "tech_stack": insight["tech_stack"],
            "source": insight["source"],
        }
    
    @router.post("/monitor-market")
    async def monitor_market(keywords: list[str] = Query(description="Keywords to monitor"), location: str = Query(default="India"), user=Depends(get_current_user)):
        """Monitor job market across all platforms."""
        from social_intel import monitor_job_market
        
        results = monitor_job_market(keywords=keywords, location=location)
        
        return {
            "keywords": keywords,
            "location": location,
            "total_jobs": results["total_jobs"],
            "by_source": results["by_source"],
            "top_jobs": results["jobs"][:20],
        }
    
    @router.get("/status")
    async def social_intel_status(user=Depends(get_current_user)):
        """Check status of social intelligence channels."""
        from social_intel import get_channel_status
        
        return {"channels": get_channel_status()}
    
    return router
