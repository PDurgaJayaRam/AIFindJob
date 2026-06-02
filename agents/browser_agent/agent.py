"""Browser Agent - AI-powered browser interaction with tool use."""
import json
import re
from typing import List, Dict, Any, Optional
from ai.ai_client import get_ai_client
from agents.browser_agent.browser_controller import BrowserController
from agents.browser_agent.autonomous_agent import AutonomousAgent


class BrowserAgent:
    """
    AI agent that interacts with websites using tools.
    Can navigate, click, type, scroll, and extract data.
    """

    def __init__(self, headless: bool = False):
        self.ai = get_ai_client()
        self.browser = BrowserController(headless=headless)
        self.autonomous = AutonomousAgent(headless=headless)
        self.max_steps = 15
        self._log_entries = []

    def _log(self, message: str):
        """Log message."""
        self._log_entries.append(message)
        print(f"[BROWSER_AGENT] {message}", flush=True)

    def _get_tools_description(self) -> str:
        """Describe available tools to AI."""
        return """Available tools (respond with JSON):

1. go_to_url - Navigate to a URL
   {"tool": "go_to_url", "url": "https://example.com"}

2. click - Click an element by text or selector
   {"tool": "click", "selector": "Close button text"}
   {"tool": "click", "selector": ".close-button"}

3. click_index - Click element by index from clickable list
   {"tool": "click_index", "index": 5}

4. type - Type text into input
   {"tool": "type", "selector": "input#search", "text": "Python"}

5. scroll - Scroll page
   {"tool": "scroll", "direction": "down", "amount": 500}
   {"tool": "scroll", "direction": "bottom"}

6. wait - Wait for page to load
   {"tool": "wait", "seconds": 3}

7. extract_jobs - Extract job listings from current page
   {"tool": "extract_jobs"}

8. get_content - Get page text content
   {"tool": "get_content"}

9. get_clickable - Get list of clickable elements
   {"tool": "get_clickable"}

10. done - Task complete, return results
    {"tool": "done", "result": "Found 20 jobs"}"""

    async def run_task(self, task: str, target_count: int = 20, keywords: str = "", is_fresher: bool = False, location: str = "Hyderabad", portals: List[str] = None, is_us: bool = False) -> List[Dict]:
        """Run a browser automation task using autonomous vision-based navigation."""
        self._log(f"Task: {task}")
        self._log(f"Target: {target_count} jobs")
        self._log(f"Keywords: {keywords}")
        self._log(f"Fresher: {is_fresher}")
        self._log(f"Location: {location}")

        self._keywords = keywords or "python java sql"
        self._is_fresher = is_fresher
        self._location = location
        self._portals = portals or ["naukri", "linkedin", "cutshort", "timesjobs", "shine", "foundit", "indeed"]

        try:
            all_jobs = await self.autonomous.run_task(
                task=task,
                target_count=target_count,
                keywords=keywords,
                is_fresher=is_fresher,
                location=location,
                portals=portals,
                is_us=is_us,
            )
            self._log_entries.extend(self.autonomous.get_log())
            self._log(f"Final: {len(all_jobs)} jobs collected")
            return all_jobs
        except Exception as e:
            self._log(f"Error: {e}")
            return []

    def get_log(self) -> List[str]:
        """Get execution log."""
        return self._log_entries
