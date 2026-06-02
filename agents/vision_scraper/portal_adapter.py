"""Portal adapter for managing job portal configurations."""

from typing import Dict, List
from urllib.parse import quote, urljoin


PORTALS: Dict[str, Dict] = {
    "naukri": {
        "name": "Naukri",
        "base_url": "https://www.naukri.com",
        "search_url": "https://www.naukri.com/{query}-jobs-in-{location}",
        "country": "in",
    },
    "indeed_in": {
        "name": "Indeed India",
        "base_url": "https://in.indeed.com",
        "search_url": "https://in.indeed.com/jobs?q={query}&l={location}",
        "country": "in",
    },
    "linkedin": {
        "name": "LinkedIn",
        "base_url": "https://www.linkedin.com",
        "search_url": "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}",
        "country": "global",
    },
    "timesjobs": {
        "name": "TimesJobs",
        "base_url": "https://www.timesjobs.com",
        "search_url": "https://www.timesjobs.com/candidate/job-search.html?from=submit&actualTxtKeywords={query}&searchBy=1&fjType=1&jobType=1&locationType=1&location={location}",
        "country": "in",
    },
    "shine": {
        "name": "Shine",
        "base_url": "https://www.shine.com",
        "search_url": "https://www.shine.com/search?q={query}&location={location}",
        "country": "in",
    },
    "foundit": {
        "name": "Foundit",
        "base_url": "https://www.foundit.in",
        "search_url": "https://www.foundit.in/srp/results?query={query}&locations={location}",
        "country": "in",
    },
    "cutshort": {
        "name": "CutShort",
        "base_url": "https://cutshort.io",
        "search_url": "https://cutshort.io/jobs?utm_source=navigation&utm_medium=menu&job_type=0&location={location}",
        "country": "in",
    },
    "glassdoor_in": {
        "name": "Glassdoor India",
        "base_url": "https://www.glassdoor.co.in",
        "search_url": "https://www.glassdoor.co.in/Job/{query}-{location}-jobs-SRCH_IL.0,{loc_len}_KO{kw_start},{kw_end}.htm",
        "country": "in",
    },
    "indeed_us": {
        "name": "Indeed USA",
        "base_url": "https://www.indeed.com",
        "search_url": "https://www.indeed.com/jobs?q={query}&l={location}",
        "country": "us",
    },
    "linkedin_us": {
        "name": "LinkedIn USA",
        "base_url": "https://www.linkedin.com",
        "search_url": "https://www.linkedin.com/jobs/search/?keywords={query}&location=United%20States",
        "country": "us",
    },
    "glassdoor_us": {
        "name": "Glassdoor USA",
        "base_url": "https://www.glassdoor.com",
        "search_url": "https://www.glassdoor.com/Job/{query}-{location}-jobs-SRCH_IL.0,{loc_len}_KO{kw_start},{kw_end}.htm",
        "country": "us",
    },
    "ziprecruiter": {
        "name": "ZipRecruiter",
        "base_url": "https://www.ziprecruiter.com",
        "search_url": "https://www.ziprecruiter.com/jobs/search?search={query}&location={location}",
        "country": "us",
    },
    "monster_us": {
        "name": "Monster USA",
        "base_url": "https://www.monster.com",
        "search_url": "https://www.monster.com/jobs/search?q={query}&where={location}",
        "country": "us",
    },
}


class PortalAdapter:
    """Manages job portal configurations and URL building."""

    def get_portal_url(self, portal_name: str) -> str:
        """Get base URL for a portal."""
        if portal_name not in PORTALS:
            raise ValueError(f"Unknown portal: {portal_name}. Supported: {list(PORTALS.keys())}")
        return PORTALS[portal_name]["base_url"]

    def build_search_url(self, portal_name: str, query: str, location: str = "") -> str:
        """Build search URL for a portal with query parameters."""
        if portal_name not in PORTALS:
            raise ValueError(f"Unknown portal: {portal_name}")

        config = PORTALS[portal_name]
        encoded_query = quote(query)
        encoded_location = quote(location) if location else ""

        search_url = config["search_url"]

        # Glassdoor needs dynamic offset calculation for SRCH_IL and KO parameters
        if "glassdoor" in portal_name and "{kw_start}" in search_url:
            loc_dash = location.replace(" ", "-")
            kw_dash = query.replace(" ", "-")
            ko_start = len(loc_dash) + 1
            ko_end = ko_start + len(kw_dash)
            search_url = search_url.replace("{query}", kw_dash)
            search_url = search_url.replace("{location}", loc_dash)
            search_url = search_url.replace("{loc_len}", str(len(loc_dash)))
            search_url = search_url.replace("{kw_start}", str(ko_start))
            search_url = search_url.replace("{kw_end}", str(ko_end))
        else:
            if "{query}" in search_url:
                search_url = search_url.replace("{query}", encoded_query)
            if "{location}" in search_url:
                search_url = search_url.replace("{location}", encoded_location)

        return search_url

    def get_portal_config(self, portal_name: str) -> Dict:
        """Get full configuration for a portal."""
        if portal_name not in PORTALS:
            raise ValueError(f"Unknown portal: {portal_name}")
        return PORTALS[portal_name].copy()

    def list_supported_portals(self) -> List[str]:
        """List all supported portal names."""
        return list(PORTALS.keys())

    def get_portals_by_country(self, country: str) -> List[str]:
        """Get portal names filtered by country."""
        return [
            name for name, config in PORTALS.items()
            if config["country"] == country or config["country"] == "global"
        ]
