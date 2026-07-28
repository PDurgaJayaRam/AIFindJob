"""Job discovery agent - uses AI browser agent to interact with websites."""
import os
import sys
import json
import logging
import subprocess
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class JobDiscoveryAgent:
    """Searches job boards using AI browser agent that can interact with websites."""

    def __init__(self):
        self.headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"

    @property
    def project_root(self):
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    async def search_jobs(
        self,
        keywords: List[str],
        locations: List[str],
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """Run AI browser agent in a subprocess."""
        query = " ".join(keywords)
        location = " ".join(locations)

        # Live monitor: notify that scraping is starting
        try:
            from agents.browser_agent.live_monitor import live_monitor
            live_monitor.update_status(
                portal="Multi-Portal",
                action=f"Starting search: '{query}' in '{location}'"
            )
        except Exception:
            pass

        try:
            script_path = os.path.join(self.project_root, "agents", "browser_agent", "standalone.py")
            # Mark subprocess so live_monitor writes to IPC file
            env = os.environ.copy()
            env["LIVE_SCRAPER_SUBPROCESS"] = "1"
            result = subprocess.run(
                [sys.executable, script_path, query, location, str(max_results), str(self.headless).lower()],
                capture_output=True, text=True, timeout=600,
                cwd=self.project_root,
                env=env
            )

            # Print agent logs for debugging
            for line in result.stdout.split('\n'):
                if line.startswith('[LOG]') or line.startswith('[BROWSER_AGENT]'):
                    print(line, flush=True)

            # Parse JSON output (last line)
            for line in reversed(result.stdout.split('\n')):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    jobs = json.loads(line)
                    if jobs:
                        print(f"Browser agent found {len(jobs)} jobs", flush=True)
                        return jobs

            # Check stderr for errors
            if result.stderr:
                print(f"Browser agent stderr: {result.stderr[:500]}", flush=True)

        except subprocess.TimeoutExpired:
            logger.warning("Browser agent timed out (600s) - scraping failed, no fake data fallback")
            # Do NOT return sample jobs - alert instead
            raise RuntimeError(f"Job discovery timed out after 600s - no jobs scraped for '{query}' in '{location}'")
        except Exception as e:
            logger.error(f"Browser agent error: {e}")
            # Do NOT return sample jobs - alert instead
            raise RuntimeError(f"Job discovery failed: {e}")

        # Should not reach here - errors raise exceptions above
        return []

    async def fetch_job_details(self, job_url: str) -> Dict[str, Any]:
        return {"description": ""}