"""
Live Scraper Monitor - Captures browser screenshots and status for live viewing.
Uses file-based IPC so subprocess browser agent can share screenshots with main server.
"""
import os
import json
import time
import asyncio
import base64
import logging
from datetime import datetime
from typing import Dict, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# Shared file path for IPC between subprocess and main server
LIVE_STATUS_FILE = os.path.join(
    os.environ.get("DATA_DIR", "data"),
    "live_scraper_status.json"
)
LIVE_SCREENSHOT_FILE = os.path.join(
    os.environ.get("DATA_DIR", "data"),
    "live_scraper_screenshot.png"
)

# Ensure data dir exists
os.makedirs(os.path.dirname(LIVE_STATUS_FILE), exist_ok=True)


def _write_status_to_file(status: Dict):
    """Write status to file for IPC."""
    try:
        # Don't include base64 in status file (too large); just reference
        status_copy = {k: v for k, v in status.items() if k != "screenshot"}
        status_copy["has_screenshot"] = status.get("screenshot") is not None
        with open(LIVE_STATUS_FILE, "w") as f:
            json.dump(status_copy, f, default=str)
    except Exception as e:
        logger.warning(f"Failed to write status file: {e}")


def _write_screenshot_to_file(screenshot_b64: str):
    """Write screenshot binary to file for IPC."""
    try:
        screenshot_bytes = base64.b64decode(screenshot_b64)
        with open(LIVE_SCREENSHOT_FILE, "wb") as f:
            f.write(screenshot_bytes)
    except Exception as e:
        logger.warning(f"Failed to write screenshot file: {e}")


def _read_screenshot_from_file() -> Optional[str]:
    """Read screenshot from file as base64."""
    try:
        if os.path.exists(LIVE_SCREENSHOT_FILE):
            with open(LIVE_SCREENSHOT_FILE, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to read screenshot file: {e}")
    return None


class LiveScraperMonitor:
    """
    Singleton that tracks live scraping activity.
    Captures screenshots, current URL, actions, and job extraction stats.
    Uses file-based IPC to share state between subprocess and main process.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._is_subprocess = os.environ.get("LIVE_SCRAPER_SUBPROCESS") == "1"
        self.is_running = False
        self.current_portal = None
        self.current_url = None
        self.current_action = "Idle"
        self.current_screenshot = None  # base64 string
        self.action_log: List[Dict] = []
        self.jobs_found: List[Dict] = []
        self.start_time = None
        self.last_update = None
        self.total_jobs_scraped = 0
        self.errors: List[str] = []
        self._mem_lock = Lock()
        self._screenshot_dir = os.path.join(os.environ.get("DATA_DIR", "data"), "screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)

    def start_session(self):
        """Start a new scraping session."""
        with self._mem_lock:
            self.is_running = True
            self.start_time = datetime.now().isoformat()
            self.current_action = "Initializing browser..."
            self.action_log = []
            self.jobs_found = []
            self.total_jobs_scraped = 0
            self.errors = []
        self._flush_to_file()
        logger.info("Live scraper session started (subprocess=%s)", self._is_subprocess)

    def stop_session(self):
        """Stop the current scraping session."""
        with self._mem_lock:
            self.is_running = False
            self.current_action = "Session ended"
        self._flush_to_file()
        logger.info("Live scraper session stopped")

    def update_status(self, portal: str = None, url: str = None, action: str = None):
        """Update the current scraping status."""
        with self._mem_lock:
            if portal:
                self.current_portal = portal
            if url:
                self.current_url = url
            if action:
                self.current_action = action
                self.action_log.append({
                    "time": datetime.now().isoformat(),
                    "action": action,
                    "portal": self.current_portal,
                    "url": self.current_url
                })
                if len(self.action_log) > 50:
                    self.action_log = self.action_log[-50:]
            self.last_update = datetime.now().isoformat()
        self._flush_to_file()

    def set_screenshot(self, page=None, screenshot_bytes=None):
        """Capture a screenshot. Pass a Playwright page (sync) or raw screenshot_bytes."""
        try:
            if screenshot_bytes is None and page is not None:
                screenshot_bytes = page.screenshot(type="jpeg", full_page=False, quality=50)
            if screenshot_bytes is None:
                return
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            with self._mem_lock:
                self.current_screenshot = screenshot_b64
                self.last_update = datetime.now().isoformat()

            if self._is_subprocess:
                _write_screenshot_to_file(screenshot_b64)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            portal_name = self.current_portal or "unknown"
            filename = f"{self._screenshot_dir}/{portal_name}_{timestamp}.jpg"
            try:
                with open(filename, "wb") as f:
                    f.write(screenshot_bytes)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Screenshot capture failed: {e}")

    def add_job(self, job: Dict):
        """Record a job that was found."""
        with self._mem_lock:
            self.jobs_found.append({
                "time": datetime.now().isoformat(),
                "title": job.get("title", "Unknown"),
                "company": job.get("company", "Unknown"),
                "location": job.get("location", ""),
                "portal": self.current_portal
            })
            self.total_jobs_scraped += 1
            if len(self.jobs_found) > 100:
                self.jobs_found = self.jobs_found[-100:]
        self._flush_to_file()

    def add_error(self, error: str):
        """Record an error."""
        with self._mem_lock:
            self.errors.append({
                "time": datetime.now().isoformat(),
                "error": error
            })
            if len(self.errors) > 20:
                self.errors = self.errors[-20:]
        self._flush_to_file()

    def _flush_to_file(self):
        """Write current status to file (for subprocess IPC)."""
        if not self._is_subprocess:
            return
        try:
            with self._mem_lock:
                _write_status_to_file({
                    "is_running": self.is_running,
                    "current_portal": self.current_portal,
                    "current_url": self.current_url,
                    "current_action": self.current_action,
                    "action_log": self.action_log[-20:],
                    "jobs_found": self.jobs_found[-20:],
                    "total_jobs_scraped": self.total_jobs_scraped,
                    "errors": self.errors[-10:],
                    "start_time": self.start_time,
                    "last_update": self.last_update,
                })
        except Exception as e:
            logger.warning(f"Flush to file failed: {e}")

    def get_status(self) -> Dict:
        """Get the current status snapshot.
        In main process: prefer own state, but merge in subprocess updates from file.
        In subprocess: return own state.
        """
        # If we're the main process, also pull updates from subprocess file
        if not self._is_subprocess:
            self._pull_from_file()

        with self._mem_lock:
            return {
                "is_running": self.is_running,
                "current_portal": self.current_portal,
                "current_url": self.current_url,
                "current_action": self.current_action,
                "screenshot": self.current_screenshot,
                "action_log": self.action_log[-20:],
                "jobs_found": self.jobs_found[-20:],
                "total_jobs_scraped": self.total_jobs_scraped,
                "errors": self.errors[-10:],
                "start_time": self.start_time,
                "last_update": self.last_update,
                "elapsed_seconds": (
                    (datetime.now() - datetime.fromisoformat(self.start_time)).total_seconds()
                    if self.start_time else 0
                )
            }

    def _pull_from_file(self):
        """Main process: pull latest status from subprocess file."""
        try:
            if not os.path.exists(LIVE_STATUS_FILE):
                return
            # Only pull if file is newer than our last update
            file_mtime = os.path.getmtime(LIVE_STATUS_FILE)
            if self.last_update:
                last_update_dt = datetime.fromisoformat(self.last_update).timestamp()
                if file_mtime <= last_update_dt:
                    return

            with open(LIVE_STATUS_FILE, "r") as f:
                file_status = json.load(f)

            with self._mem_lock:
                self.is_running = file_status.get("is_running", False)
                self.current_portal = file_status.get("current_portal")
                self.current_url = file_status.get("current_url")
                self.current_action = file_status.get("current_action", "Idle")
                self.action_log = file_status.get("action_log", [])
                self.jobs_found = file_status.get("jobs_found", [])
                self.total_jobs_scraped = file_status.get("total_jobs_scraped", 0)
                self.errors = file_status.get("errors", [])
                self.start_time = file_status.get("start_time")
                self.last_update = file_status.get("last_update")

            # Pull screenshot from separate file
            screenshot = _read_screenshot_from_file()
            if screenshot:
                with self._mem_lock:
                    self.current_screenshot = screenshot
        except Exception as e:
            logger.warning(f"Pull from file failed: {e}")


# Global instance
live_monitor = LiveScraperMonitor()
