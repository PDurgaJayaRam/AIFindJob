"""Central agent orchestrator that coordinates all sub-agents."""
import asyncio
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from agents.job_discovery.discovery import JobDiscoveryAgent
from agents.job_intelligence.intelligence import JobIntelligenceAgent
from agents.resume_match.matcher import ResumeMatchAgent
from agents.company_intelligence.intel import CompanyIntelAgent
from agents.people_finder.finder import PeopleFinderAgent
from agents.networking.messages import NetworkingAgent
from agents.auto_apply.browser_agent import AutoApplyAgent
from agents.tracking.tracker import TrackingAgent


@dataclass
class OrchestratorResult:
    jobs_discovered: int = 0
    jobs_analyzed: int = 0
    jobs_matched: int = 0
    applications_submitted: int = 0
    leads_generated: int = 0
    messages_generated: int = 0
    errors: List[str] = None
    jobs: List[Dict[str, Any]] = None
    leads: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.jobs is None:
            self.jobs = []
        if self.leads is None:
            self.leads = []


class AgentOrchestrator:
    """Coordinates the full career + lead generation pipeline."""

    def __init__(self):
        self.discovery = JobDiscoveryAgent()
        self.intelligence = JobIntelligenceAgent()
        self.resume_match = ResumeMatchAgent()
        self.company_intel = CompanyIntelAgent()
        self.people_finder = PeopleFinderAgent()
        self.networking = NetworkingAgent()
        self.auto_apply = AutoApplyAgent()
        self.tracker = TrackingAgent()

    async def run_job_pipeline(
        self,
        resume_text: str,
        keywords: List[str],
        locations: List[str],
        auto_apply: bool = False,
        match_threshold: float = 75.0,
        max_jobs: int = 20,
    ) -> OrchestratorResult:
        """Run the full job discovery -> match -> apply pipeline."""
        result = OrchestratorResult()

        # 1. Discover jobs with visible browser
        try:
            raw_jobs = await self.discovery.search_jobs(
                keywords=keywords,
                locations=locations,
                max_results=max_jobs,
            )
            result.jobs_discovered = len(raw_jobs)
        except Exception as e:
            # Try direct AutonomousAgent as fallback (avoids subprocess issues)
            result.errors.append(f"Job discovery subprocess failed: {e}, trying direct method")
            try:
                from agents.browser_agent.autonomous_agent import AutonomousAgent
                import os
                agent = AutonomousAgent(headless=False, proxy=os.environ.get("BROWSER_PROXY"))
                is_fresher = True  # Default for freshers
                raw_jobs = await agent.run_task(
                    task=f"Search for {keywords} jobs in {locations}",
                    target_count=max_jobs,
                    keywords=",".join(keywords),
                    is_fresher=is_fresher,
                    location=",".join(locations),
                    portals=["naukri", "indeed", "shine", "foundit", "timesjobs"],
                    overall_timeout=300,
                )
                result.jobs_discovered = len(raw_jobs)
                result.errors.append(f"Direct AutonomousAgent succeeded with {len(raw_jobs)} jobs")
            except Exception as fallback_e:
                result.errors.append(f"Job discovery failed (both methods): {fallback_e}")
                return result

        # 2. Analyze & match
        matched_jobs = []
        for job in raw_jobs:
            try:
                analysis = await self.intelligence.analyze_job(job)
                job.update(analysis)
                result.jobs_analyzed += 1

                match = await self.resume_match.compare(resume_text, job)
                job["match_score"] = match.get("match_score", 0)
                job["ats_score"] = match.get("ats_score", 0)
                job["missing_skills"] = match.get("missing_skills", [])

                if job["match_score"] >= match_threshold:
                    matched_jobs.append(job)
                    result.jobs_matched += 1
                result.jobs.append(job)
            except Exception as e:
                result.errors.append(f"Analysis failed for {job.get('title', 'unknown')}: {e}")

        # 3. Auto-apply (if enabled)
        if auto_apply:
            for job in matched_jobs:
                try:
                    if job.get("apply_url"):
                        success = await self.auto_apply.apply_to_job(job, resume_text)
                        if success:
                            result.applications_submitted += 1
                except Exception as e:
                    result.errors.append(f"Auto-apply failed for {job.get('title', 'unknown')}: {e}")

        return result

    async def run_lead_pipeline(
        self,
        companies: List[Dict[str, Any]],
        target_niche: Optional[str] = None,
    ) -> OrchestratorResult:
        """Run the company intelligence + lead generation pipeline."""
        result = OrchestratorResult()

        for company in companies:
            try:
                # Analyze company for pain signals & intel
                intel = await self.company_intel.analyze_company(company)
                company.update(intel)
                result.leads_generated += 1

                # Find people
                people = await self.people_finder.find_people(company)
                company["contacts"] = people

                # Generate outreach
                for person in people[:3]:
                    msg = await self.networking.generate_lead_outreach(company, person)
                    person["outreach_message"] = msg
                    result.messages_generated += 1
            except Exception as e:
                result.errors.append(f"Lead pipeline failed for {company.get('name', 'unknown')}: {e}")

        return result

    async def run_full_combo(
        self,
        resume_text: str,
        keywords: List[str],
        locations: List[str],
        companies: Optional[List[Dict]] = None,
        auto_apply: bool = False,
        match_threshold: float = 75.0,
    ) -> Dict[str, Any]:
        """Run both job and lead pipelines concurrently."""
        job_task = self.run_job_pipeline(
            resume_text=resume_text,
            keywords=keywords,
            locations=locations,
            auto_apply=auto_apply,
            match_threshold=match_threshold,
        )
        lead_task = None
        if companies:
            lead_task = self.run_lead_pipeline(companies)

        if lead_task:
            job_result, lead_result = await asyncio.gather(job_task, lead_task, return_exceptions=True)
        else:
            job_result = await job_task
            lead_result = OrchestratorResult()

        return {
            "job_pipeline": {
                "jobs_discovered": job_result.jobs_discovered if isinstance(job_result, OrchestratorResult) else 0,
                "jobs_matched": job_result.jobs_matched if isinstance(job_result, OrchestratorResult) else 0,
                "applications_submitted": job_result.applications_submitted if isinstance(job_result, OrchestratorResult) else 0,
                "errors": job_result.errors if isinstance(job_result, OrchestratorResult) else [str(job_result)],
            },
            "lead_pipeline": {
                "leads_generated": lead_result.leads_generated if isinstance(lead_result, OrchestratorResult) else 0,
                "messages_generated": lead_result.messages_generated if isinstance(lead_result, OrchestratorResult) else 0,
                "errors": lead_result.errors if isinstance(lead_result, OrchestratorResult) else [str(lead_result)],
            },
        }
