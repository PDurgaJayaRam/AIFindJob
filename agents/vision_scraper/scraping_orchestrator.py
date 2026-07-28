"""Scraping Orchestrator - Coordinates all vision scraping components."""

import time
import logging
import asyncio
from typing import Dict, List, Optional

from agents.vision_scraper.models import (
    ScrapingResult,
    NavigationStatus,
    JobData,
    ExtractionMethod,
)
from agents.vision_scraper.rate_limiter import RateLimiter
from agents.vision_scraper.multi_provider_client import MultiProviderAIClient
from agents.vision_scraper.vision_agent import VisionAgent
from agents.vision_scraper.hybrid_extractor import HybridExtractor
from agents.vision_scraper.portal_adapter import PortalAdapter
from agents.vision_scraper.config import ScrapingConfig
from agents.browser_agent.browser_controller import BrowserController

logger = logging.getLogger(__name__)


class ScrapingOrchestrator:
    """Orchestrates vision-guided scraping across job portals."""

    def __init__(
        self,
        config: Optional[ScrapingConfig] = None,
        browser: Optional[BrowserController] = None,
    ):
        self.config = config or ScrapingConfig.from_env()
        errors = self.config.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        self.browser = browser or BrowserController(headless=self.config.browser.headless)
        self.rate_limiter = RateLimiter()
        self.rate_limiter.configure_provider("nvidia", self.config.rate_limit.nvidia_rpm)
        self.rate_limiter.configure_provider("mistral", self.config.rate_limit.mistral_rpm)
        self.rate_limiter.configure_provider("gemini", self.config.rate_limit.gemini_rpm)

        self.ai_client = MultiProviderAIClient(rate_limiter=self.rate_limiter)
        self.vision_agent = VisionAgent(
            browser=self.browser,
            ai_client=self.ai_client,
            rate_limiter=self.rate_limiter,
            max_steps=self.config.navigation.max_steps,
        )
        self.extractor = HybridExtractor(
            browser=self.browser,
            vision_agent=self.vision_agent,
            max_jobs=self.config.extraction.max_jobs_per_portal,
            max_scroll_attempts=self.config.extraction.max_scroll_attempts,
        )
        self.portal_adapter = PortalAdapter()

    async def _save_jobs_to_db(self, jobs: List[JobData]):
        """Persist jobs to database."""
        try:
            from agents.job_saver import save_jobs
            save_jobs(jobs)
            logger.info(f"Saved {len(jobs)} jobs to database")
        except Exception as e:
            logger.error(f"Failed to save jobs to database: {e}")

    async def scrape_portal(
        self,
        portal_name: str,
        query: str,
        location: str = "",
        max_jobs: Optional[int] = None,
    ) -> ScrapingResult:
        """Scrape a single portal for jobs."""
        start_time = time.time()
        max_jobs = max_jobs or self.config.extraction.max_jobs_per_portal

        logger.info(f"Starting scrape of {portal_name} for '{query}' in '{location}'")

        try:
            if not self.browser.page:
                await self.browser.start()

            search_url = self.portal_adapter.build_search_url(portal_name, query, location)
            logger.info(f"Navigating to {search_url}")

            nav_result = await self.vision_agent.navigate_to_search(
                portal_url=search_url,
                query=query,
                location=location,
            )

            if nav_result.status != NavigationStatus.SUCCESS:
                return ScrapingResult(
                    portal_name=portal_name,
                    status=nav_result.status,
                    steps_taken=nav_result.steps_taken,
                    actions_taken=nav_result.actions,
                    screenshots_taken=nav_result.screenshots_taken,
                    time_elapsed_ms=int((time.time() - start_time) * 1000),
                    error_message=nav_result.error_message,
                )

            await self.browser.wait(self.config.extraction.scroll_wait_seconds)

            jobs = await self.extractor.extract_jobs(portal_name, max_jobs=max_jobs)
            self.extractor.max_jobs = max_jobs

            if jobs:
                await self._save_jobs_to_db(jobs)

            return ScrapingResult(
                portal_name=portal_name,
                status=NavigationStatus.SUCCESS,
                jobs=jobs,
                steps_taken=nav_result.steps_taken,
                actions_taken=nav_result.actions,
                screenshots_taken=nav_result.screenshots_taken,
                extraction_method=ExtractionMethod.HYBRID,
                time_elapsed_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            logger.error(f"Scraping failed for {portal_name}: {e}")
            return ScrapingResult(
                portal_name=portal_name,
                status=NavigationStatus.FAILED,
                steps_taken=0,
                time_elapsed_ms=int((time.time() - start_time) * 1000),
                error_message=str(e),
            )

    async def scrape_all_portals(
        self,
        query: str,
        location: str = "",
        portal_names: Optional[List[str]] = None,
        max_jobs_per_portal: Optional[int] = None,
    ) -> Dict[str, ScrapingResult]:
        """Scrape multiple portals sequentially."""
        if portal_names is None:
            portal_names = self.portal_adapter.list_supported_portals()

        results = {}
        for portal_name in portal_names:
            try:
                logger.info(f"Processing portal {portal_name} ({portal_names.index(portal_name)+1}/{len(portal_names)})")
                result = await self.scrape_portal(
                    portal_name=portal_name,
                    query=query,
                    location=location,
                    max_jobs=max_jobs_per_portal,
                )
                results[portal_name] = result
                logger.info(f"Portal {portal_name}: {result.status} - {len(result.jobs)} jobs")
            except Exception as e:
                logger.error(f"Portal {portal_name} failed: {e}")
                results[portal_name] = ScrapingResult(
                    portal_name=portal_name,
                    status=NavigationStatus.FAILED,
                    error_message=str(e),
                )

        total_jobs = sum(len(r.jobs) for r in results.values())
        successful = sum(1 for r in results.values() if r.status == NavigationStatus.SUCCESS)
        logger.info(f"Batch scraping complete: {successful}/{len(portal_names)} portals, {total_jobs} total jobs")
        return results

    async def handle_scraping_error(self, portal_name: str, error: Exception, retry_count: int = 0):
        """Handle scraping errors with retry logic."""
        max_retries = 2
        if retry_count >= max_retries:
            logger.error(f"Max retries reached for {portal_name}")
            return False

        backoff = 2 ** retry_count
        logger.info(f"Retrying {portal_name} after {backoff}s (attempt {retry_count + 1})")
        await asyncio.sleep(backoff)

        if self.browser.is_browser_crashed():
            logger.info("Browser crashed, restarting...")
            try:
                await self.browser.close()
            except:
                pass
            await self.browser.start()

        return True

    async def close(self):
        """Clean up resources."""
        try:
            await self.browser.close()
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
