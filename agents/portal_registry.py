"""Portal Registry - Centralized management of job portals.

Each portal has:
- URL patterns for search
- CSS selectors for job extraction
- Rate limiting configuration
- Status (enabled/disabled)
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PortalStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"


@dataclass
class PortalConfig:
    """Configuration for a job portal."""
    name: str
    display_name: str
    base_url: str
    search_url_template: str
    enabled: bool = True
    rate_limit_per_minute: int = 10
    rate_limit_per_hour: int = 100
    requires_proxy: bool = False
    supports_location: bool = True
    supports_keywords: bool = True
    country: str = "global"  # "india", "us", "global"
    
    # CSS selectors for job extraction
    selectors: Dict[str, str] = field(default_factory=dict)
    
    # Rate limiting state
    _request_count_minute: int = 0
    _request_count_hour: int = 0
    _last_minute_reset: float = 0
    _last_hour_reset: float = 0
    
    def __post_init__(self):
        """Initialize default selectors if not provided."""
        if not self.selectors:
            self.selectors = self._get_default_selectors()
    
    def _get_default_selectors(self) -> Dict[str, str]:
        """Get default CSS selectors based on portal name."""
        selectors = {
            # Job listing container
            "job_list": ".job-card, .job-listing, .job-item, [data-testid='job-card']",
            
            # Job title
            "job_title": "h2, h3, .job-title, [class*='title'], a[class*='job']",
            
            # Company name
            "company": ".company-name, [class*='company'], [class*='employer']",
            
            # Location
            "location": ".location, [class*='location'], [data-testid='location']",
            
            # Job URL
            "job_url": "a[href*='job'], a[href*='position'], a[href*='detail']",
            
            # Description snippet
            "description": ".description, .snippet, [class*='desc']",
            
            # Experience
            "experience": ".experience, [class*='experience'], [class*='exp']",
            
            # Salary
            "salary": ".salary, [class*='salary'], [class*='compensation']",
        }
        
        # Portal-specific overrides
        if self.name == "internshala":
            selectors.update({
                "job_list": ".individual_card, .internship-card",
                "job_title": ".job-internship-heading, h3",
                "company": ".company-name, .link",
                "location": ".location, .item-location",
                "job_url": "a[href*='internship']",
            })
        elif self.name == "wellfound":
            selectors.update({
                "job_list": ".styles_job__sT0xq, [class*='job-card']",
                "job_title": ".styles_jobTitle__h1ByP, h4",
                "company": ".styles_companyName__28dnB, .company-name",
                "location": ".styles_jobLocation__Dp7JH, .location",
            })
        elif self.name == "hired":
            selectors.update({
                "job_list": ".job-card, .position-card",
                "job_title": ".job-title, h3",
                "company": ".company-name, .employer",
                "location": ".location, .job-location",
            })
        
        return selectors


# Portal Registry
PORTAL_REGISTRY: Dict[str, PortalConfig] = {
    # ─── India Portals ───────────────────────────────────────────────────────
    "naukri": PortalConfig(
        name="naukri",
        display_name="Naukri",
        base_url="https://www.naukri.com",
        search_url_template="https://www.naukri.com/{keyword_dash}-jobs-in-{location_dash}",
        enabled=True,
        rate_limit_per_minute=5,
        rate_limit_per_hour=50,
        country="india",
        selectors={
            "job_list": ".srp-cardlisting, .jobTuple, [class*='job-card']",
            "job_title": ".title, .ellipsis, [class*='title'] a",
            "company": ".subTitle, [class*='company']",
            "location": ".location, [class*='location']",
            "job_url": "a.title, a[href*='job']",
            "description": ".job-description, [class*='desc']",
            "experience": ".experience, [class*='experience']",
        }
    ),
    
    "indeed": PortalConfig(
        name="indeed",
        display_name="Indeed",
        base_url="https://in.indeed.com",
        search_url_template="https://in.indeed.com/jobs?q={keyword}&l={location}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="india",
        selectors={
            "job_list": ".job_seen_beacon, .jobsearch-ResultsList > li",
            "job_title": "h2.jobTitle a, [class*='jobTitle']",
            "company": "[data-testid='company-name'], .companyName",
            "location": "[data-testid='text-location'], .companyLocation",
            "job_url": "h2.jobTitle a",
            "description": ".job-snippet, [class*='snippet']",
        }
    ),
    
    "linkedin": PortalConfig(
        name="linkedin",
        display_name="LinkedIn",
        base_url="https://www.linkedin.com",
        search_url_template="https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=5,
        rate_limit_per_hour=50,
        country="global",
        requires_proxy=True,  # LinkedIn is aggressive with blocking
        selectors={
            "job_list": ".jobs-search-results__list-item, .job-card-container",
            "job_title": ".job-card-list__title, [class*='job-card__title']",
            "company": ".job-card-container__primary-description, [class*='company']",
            "location": ".job-card-container__metadata-item, [class*='location']",
            "job_url": "a[href*='/jobs/view/']",
        }
    ),
    
    "timesjobs": PortalConfig(
        name="timesjobs",
        display_name="TimesJobs",
        base_url="https://www.timesjobs.com",
        search_url_template="https://www.timesjobs.com/candidate/job-search.html?from=submit&actualTxtKeywords={keyword}&searchBy=1&location={location}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="india",
    ),
    
    "shine": PortalConfig(
        name="shine",
        display_name="Shine",
        base_url="https://www.shine.com",
        search_url_template="https://www.shine.com/job-search/{keyword_dash}-jobs-in-{location_dash}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="india",
    ),
    
    "foundit": PortalConfig(
        name="foundit",
        display_name="Foundit",
        base_url="https://www.foundit.in",
        search_url_template="https://www.foundit.in/srp/results?query={keyword}+{location}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="india",
    ),
    
    "cutshort": PortalConfig(
        name="cutshort",
        display_name="CutShort",
        base_url="https://cutshort.io",
        search_url_template="https://cutshort.io/jobs?q={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="india",
    ),
    
    # ─── New Free Portals ────────────────────────────────────────────────────
    "internshala": PortalConfig(
        name="internshala",
        display_name="Internshala",
        base_url="https://internshala.com",
        search_url_template="https://internshala.com/internships/keyword-{keyword}/location-{location}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="india",
        selectors={
            "job_list": ".individual_card, .internship-card, [class*='card']",
            "job_title": ".job-internship-heading, h3, [class*='heading']",
            "company": ".company-name, .link, [class*='company']",
            "location": ".location, .item-location, [class*='location']",
            "job_url": "a[href*='internship']",
        }
    ),
    
    "wellfound": PortalConfig(
        name="wellfound",
        display_name="Wellfound (AngelList)",
        base_url="https://wellfound.com",
        search_url_template="https://wellfound.com/jobs?role={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="global",
        selectors={
            "job_list": "[class*='job-card'], [class*='styles_job']",
            "job_title": "[class*='jobTitle'], h4, [class*='title']",
            "company": "[class*='companyName'], .company-name",
            "location": "[class*='location'], .job-location",
        }
    ),
    
    "hired": PortalConfig(
        name="hired",
        display_name="Hired",
        base_url="https://hired.com",
        search_url_template="https://hired.com/jobs?q={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="global",
    ),
    
    # ─── US/Global Portals ───────────────────────────────────────────────────
    "linkedin_us": PortalConfig(
        name="linkedin_us",
        display_name="LinkedIn US",
        base_url="https://www.linkedin.com",
        search_url_template="https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}, United States",
        enabled=True,
        rate_limit_per_minute=5,
        rate_limit_per_hour=50,
        country="us",
        requires_proxy=True,
    ),
    
    "glassdoor": PortalConfig(
        name="glassdoor",
        display_name="Glassdoor",
        base_url="https://www.glassdoor.co.in",
        search_url_template="https://www.glassdoor.co.in/Job/{keyword_dash}-{location_dash}-jobs-SRCH_IL.0,{loc_len}_KO{ko_start},{ko_end}.htm",
        enabled=False,  # Disabled due to Cloudflare blocking
        requires_proxy=True,
        country="india",
    ),
    
    "glassdoor_us": PortalConfig(
        name="glassdoor_us",
        display_name="Glassdoor US",
        base_url="https://www.glassdoor.com",
        search_url_template="https://www.glassdoor.com/Job/{keyword_dash}-{location_dash}-jobs-SRCH_IL.0,{loc_len}_KO{ko_start},{ko_end}.htm",
        enabled=False,  # Disabled due to Cloudflare blocking
        requires_proxy=True,
        country="us",
    ),
    
    # ─── Remote/Global Portals ───────────────────────────────────────────────
    "weworkremotely": PortalConfig(
        name="weworkremotely",
        display_name="We Work Remotely",
        base_url="https://weworkremotely.com",
        search_url_template="https://weworkremotely.com/remote-jobs/search?term={keyword}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="global",
        supports_location=False,  # Remote-only
    ),
    
    "remotive": PortalConfig(
        name="remotive",
        display_name="Remotive",
        base_url="https://remotive.com",
        search_url_template="https://remotive.com/remote-jobs?search={keyword}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="global",
        supports_location=False,
    ),
    
    "remoteok": PortalConfig(
        name="remoteok",
        display_name="RemoteOK",
        base_url="https://remoteok.com",
        search_url_template="https://remoteok.com/remote-{keyword}-jobs",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="global",
        supports_location=False,
    ),
    
    # ─── India-Specific Portals (Added for Tier-2/3 College Students) ────────
    "hirist": PortalConfig(
        name="hirist",
        display_name="Hirist",
        base_url="https://www.hirist.tech",
        search_url_template="https://www.hirist.tech/jobs/search?query={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=8,
        rate_limit_per_hour=80,
        country="india",
        selectors={
            "job_list": ".job-card, [class*='job-item']",
            "job_title": "h3, [class*='title']",
            "company": "[class*='company'], .employer",
            "location": "[class*='location']",
        }
    ),
    
    "apna": PortalConfig(
        name="apna",
        display_name="Apna",
        base_url="https://apna.co",
        search_url_template="https://apna.co/jobs/search?query={keyword}&city={location}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="india",
        selectors={
            "job_list": ".job-card, [class*='job-listing']",
            "job_title": "h3, [class*='job-title']",
            "company": "[class*='company']",
            "location": "[class*='location']",
        }
    ),
    
    "instahyre": PortalConfig(
        name="instahyre",
        display_name="Instahyre",
        base_url="https://www.instahyre.com",
        search_url_template="https://www.instahyre.com/search?query={keyword}&location={location}",
        enabled=True,
        rate_limit_per_minute=5,
        rate_limit_per_hour=50,
        country="india",
        selectors={
            "job_list": ".job-card, [class*='opportunity-card']",
            "job_title": "h3, [class*='title']",
            "company": "[class*='company']",
            "location": "[class*='location']",
        }
    ),
    
    "workindia": PortalConfig(
        name="workindia",
        display_name="WorkIndia",
        base_url="https://www.workindia.in",
        search_url_template="https://www.workindia.in/search?q={keyword}&city={location}",
        enabled=True,
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
        country="india",
        selectors={
            "job_list": ".job-card, [class*='job-item']",
            "job_title": "h3, [class*='title']",
            "company": "[class*='company']",
            "location": "[class*='location']",
        }
    ),
}


def get_portal(name: str) -> Optional[PortalConfig]:
    """Get a portal configuration by name."""
    return PORTAL_REGISTRY.get(name)


def get_enabled_portals(country: str = None) -> List[PortalConfig]:
    """Get all enabled portals, optionally filtered by country."""
    portals = [
        p for p in PORTAL_REGISTRY.values()
        if p.enabled
    ]
    
    if country:
        portals = [p for p in portals if p.country == country or p.country == "global"]
    
    return portals


def get_portal_names(country: str = None) -> List[str]:
    """Get list of enabled portal names."""
    return [p.name for p in get_enabled_portals(country)]


def disable_portal(name: str, reason: str = "manual"):
    """Disable a portal."""
    if name in PORTAL_REGISTRY:
        PORTAL_REGISTRY[name].enabled = False
        logger.info(f"Disabled portal '{name}': {reason}")


def enable_portal(name: str):
    """Enable a portal."""
    if name in PORTAL_REGISTRY:
        PORTAL_REGISTRY[name].enabled = True
        logger.info(f"Enabled portal '{name}'")


def get_portal_status() -> Dict[str, Dict]:
    """Get status of all portals."""
    return {
        name: {
            "display_name": p.display_name,
            "enabled": p.enabled,
            "country": p.country,
            "rate_limit": f"{p.rate_limit_per_minute}/min, {p.rate_limit_per_hour}/hour",
            "requires_proxy": p.requires_proxy,
        }
        for name, p in PORTAL_REGISTRY.items()
    }
