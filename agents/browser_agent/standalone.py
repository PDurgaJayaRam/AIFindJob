"""Standalone browser agent - run via subprocess."""
import sys
import os
import json
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.browser_agent.agent import BrowserAgent


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Python"
    location = sys.argv[2] if len(sys.argv) > 2 else "Hyderabad"
    target = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    headless = sys.argv[4].lower() == "true" if len(sys.argv) > 4 else False
    is_fresher = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else False
    portals = sys.argv[6] if len(sys.argv) > 6 else "naukri,linkedin,cutshort,timesjobs,shine,foundit,indeed"
    is_us = sys.argv[7].lower() == "true" if len(sys.argv) > 7 else False

    logger.info(f"Starting: query={query}, location={location}, target={target}, fresher={is_fresher}, us={is_us}")
    logger.info(f"Portals: {portals}")

    agent = BrowserAgent(headless=headless)

    task = f"""Go to job portals and search for "{query}" jobs in "{location}"{" for freshers" if is_fresher else ""}.
Handle any popups, login prompts, or cookie banners by closing them.
Scroll down to load more jobs.
Extract at least {target} job listings with title, company, location, and URL.
Return when you have enough jobs or visited all portals."""

    portal_list = [p.strip() for p in portals.split(",")]
    jobs = await agent.run_task(task, target_count=target, keywords=query, is_fresher=is_fresher, location=location, portals=portal_list, is_us=is_us)

    for log_msg in agent.get_log():
        print(f"[LOG] {log_msg}", flush=True)

    print(json.dumps(jobs[:target]))


if __name__ == "__main__":
    asyncio.run(main())
