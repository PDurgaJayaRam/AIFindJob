"""Dual Model Orchestrator - Step 3.5 (Brain) + Autonomous Agent (Hands).

Architecture:
  Step 3.5 (Brain) = Planning, matching, scoring, saving
  Autonomous Agent = Vision-based portal navigation and job extraction
  No hardcoded scripts - AI agent handles any portal dynamically

Flow:
  1. Brain plans search strategy (keywords, portals)
  2. Autonomous Agent navigates portals using vision
  3. Agent extracts jobs by understanding page content
  4. Brain matches, scores, saves, responds
"""
import os
import re
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from ai.ai_client import get_ai_client

logger = logging.getLogger(__name__)

# ─── Prompts ───────────────────────────────────────────────────────────────

SEARCH_PLAN_PROMPT = """You are a job search strategist. Given the user's profile and request, create a detailed search plan.

User Profile:
- Name: {name}
- Skills: {skills}
- Experience: {experience_years} years
- Target Roles: {target_roles}
- Is Fresher: {is_fresher}

User Request: "{user_request}"
Target Job Count: {target_count}
Default Location: {location}

Create a JSON search plan with:
{{
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],
  "location": "city to search in",
  "experience_filter": "fresher or 0-2 years or any"
}}

Rules for keyword generation:
- Generate 6-8 different keyword variations for thorough coverage
- Use the user's ACTUAL skills from their profile
- Include role variations: "Skill Developer", "Skill Engineer", "Backend Developer Skill"
- If user is fresher, add: "Skill Developer Fresher", "Junior Skill Developer", "Entry Level Skill Developer"
- Include skill-specific searches: just the skill name itself
- Include generic role searches: "Software Engineer", "Backend Developer", "Full Stack Developer"
- Return ONLY valid JSON, no markdown formatting."""


class DualModelOrchestrator:
    """Continuous feedback loop between Step 3.5 (Brain) and browser automation.

    The loop:
    1. Brain creates plan with multiple keyword variations
    2. Browser navigates to search URLs directly (reliable)
    3. UI-TARS handles visual tasks (popups, scrolling)
    4. JS extraction gets job data
    5. Brain evaluates: enough jobs? If no, try more keywords
    6. Repeat until target met or max rounds exhausted
    7. Brain matches, scores, saves, responds
    """

    def __init__(self):
        self.ai = get_ai_client()
        self.browser = None
        self._seen_urls: Set[str] = set()
        self._tool_log = []
        self._used_keywords: Set[str] = set()

    def _log(self, name: str, status: str, result: str):
        self._tool_log.append({"name": name, "status": status, "result": result})
        logger.info(f"[{name}] {status}: {result}")

    def _init_browser(self):
        from agents.browser_agent.browser_controller import BrowserController
        self.browser = BrowserController(headless=False)

    async def _create_search_plan(self, user_request: str, context: Dict) -> Dict:
        """Step 3.5: Understand request and create search plan with multiple keywords."""
        profile = context.get("profile", {})
        location = context.get("location", "Hyderabad")
        target_count = context.get("target_count", 20)

        # Form experience setting overrides resume analysis
        ui_experience = context.get("experience", "").strip().lower()
        if ui_experience == "fresher":
            is_fresher = True
        elif ui_experience == "experienced":
            is_fresher = False
        elif ui_experience.isdigit():
            is_fresher = int(ui_experience) <= 2
        else:
            is_fresher = profile.get("is_fresher", True)

        prompt = SEARCH_PLAN_PROMPT.format(
            name=profile.get("name", "User"),
            skills=", ".join(profile.get("skills", [])),
            experience_years=profile.get("experience_years", 0),
            target_roles=", ".join(profile.get("target_roles", [])),
            is_fresher=is_fresher,
            user_request=user_request,
            target_count=target_count,
            location=location,
        )

        try:
            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a job search strategist. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000,
                json_mode=True,
            )

            plan = json.loads(response)
            keywords = plan.get("keywords", [])
            self._log("brain_planning", "complete", f"Generated {len(keywords)} keywords: {', '.join(keywords[:5])}")
            return plan
        except Exception as e:
            self._log("brain_planning", "error", f"AI planning failed, using fallback: {e}")
            # Fallback: generate keywords from profile skills
            skills = profile.get("skills", ["Java"])
            roles = profile.get("target_roles", [])
            keywords = []

            # Add role-based keywords first
            for role in roles[:4]:
                keywords.append(role)

            # Add skill + role combinations
            role_suffixes = ["Developer", "Engineer", "Consultant", "Analyst"]
            for skill in skills[:3]:
                keywords.append(f"{skill} Developer")
                keywords.append(f"{skill} Engineer")

            # Add generic fallbacks
            if not keywords:
                keywords = ["Java Developer", "Software Engineer", "Backend Developer"]

            # Deduplicate while preserving order
            seen = set()
            unique_keywords = []
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in seen:
                    seen.add(kw_lower)
                    unique_keywords.append(kw)

            return {
                "keywords": unique_keywords[:8],
                "location": location,
                "experience_filter": "fresher" if profile.get("is_fresher", True) else "any",
            }

    async def _generate_keywords_with_ai(self, profile: Dict, user_keywords: List[str], location: str) -> List[str]:
        """Use AI to generate smart job search keywords."""
        try:
            skills = profile.get("skills", [])
            roles = profile.get("target_roles", [])
            is_fresher = profile.get("is_fresher", True)
            experience_years = profile.get("experience_years", 0)

            prompt = f"""Generate job search keywords for this person. Return ONLY a JSON array of strings.

Profile:
- Skills: {', '.join(skills)}
- Target Roles: {', '.join(roles)}
- Experience: {experience_years} years
- Is Fresher: {is_fresher}
- Location: {location}
- User's keywords: {', '.join(user_keywords)}

Generate 10-15 search keywords that will find relevant jobs on Indian job portals (Naukri, Indeed, LinkedIn).

Rules:
1. Include the user's keywords as role-based searches: e.g. if user says "SQL", search for "SQL Developer", "Data Analyst SQL"
2. Include ALL target roles from the profile — do not skip any. For each role, generate 2-3 variations.
3. If fresher, add "Fresher", "Junior", "Entry Level", "Intern" variations for EVERY target role
4. Make keywords realistic for job search (what people actually search for)
5. Don't include HTML, CSS, SQL as standalone keywords (they're not job titles) — always combine with a role word
6. Include skill-based roles: e.g. if user has "Appian", search for "Appian Developer", "Appian Consultant", "Appian Fresher"
7. Include "Fresher" or "Junior" variations for every keyword when is_fresher is true

Return ONLY the JSON array, no explanation:
["keyword1", "keyword2", "keyword3", ...]"""

            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
            )

            # Parse response - handle various formats
            response = response.strip()

            # Remove markdown code blocks
            if '```' in response:
                import re
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
                if match:
                    response = match.group(1).strip()

            # Try to extract JSON array if response has extra text
            import re
            import json

            # Look for JSON array pattern
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                response = json_match.group(0)

            keywords = json.loads(response)

            if isinstance(keywords, list) and len(keywords) > 0:
                # Ensure user keywords are included
                for uk in reversed(user_keywords):
                    if uk not in keywords:
                        keywords.insert(0, uk)

                # Ensure ALL target roles from profile are included with variations
                for role in roles:
                    role_lower = role.lower()
                    if not any(role_lower in kw.lower() for kw in keywords):
                        keywords.append(role)
                        if is_fresher:
                            keywords.append(f"Junior {role}")
                            keywords.append(f"Entry Level {role}")
                            keywords.append(f"{role} Fresher")

                return keywords[:15]

        except Exception as e:
            self._log("brain_planning", "warning", f"AI keyword generation failed, using fallback keywords: {e}")

        # Fallback: simple keyword generation
        keywords = list(user_keywords)
        if is_fresher:
            keywords.extend(["Software Developer Fresher", "Junior Developer", "Entry Level Developer", "Software Intern", "Trainee Developer"])
            for role in roles:
                keywords.append(role)
                keywords.append(f"Junior {role}")
                keywords.append(f"{role} Fresher")
        else:
            keywords.extend(["Software Developer", "Software Engineer", "Backend Developer"])
            for role in roles:
                keywords.append(role)
        return keywords[:15]

    def _build_search_url(self, keyword: str, location: str, portal: str = "naukri") -> str:
        """Build direct search URL for a portal. Experience filtering is done post-scrape."""
        kw = keyword.replace(" ", "%20")
        loc = location.replace(" ", "%20")
        kw_dash = keyword.replace(" ", "-")
        loc_dash = location.replace(" ", "-")

        if portal == "naukri":
            return f"https://www.naukri.com/{kw_dash}-jobs-in-{loc_dash}"
        elif portal == "indeed":
            return f"https://in.indeed.com/jobs?q={kw}&l={loc}"
        elif portal == "linkedin":
            return f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}"
        elif portal == "cutshort":
            return f"https://cutshort.io/jobs?q={kw}&location={loc}"
        elif portal == "foundit":
            return f"https://www.foundit.in/srp/results?query={kw}+{loc}"
        elif portal == "timesjobs":
            return f"https://www.timesjobs.com/candidate/job-search.html?from=submit&actualTxtKeywords={kw}&searchBy=1&fjType=1&jobType=1&locationType=1&location={loc}"
        elif portal == "shine":
            return f"https://www.shine.com/job-search/{kw_dash}-jobs-in-{loc_dash}"
        elif portal == "glassdoor":
            ko_s = len(loc_dash) + 1
            ko_e = ko_s + len(kw_dash)
            return f"https://www.glassdoor.co.in/Job/{kw_dash}-{loc_dash}-jobs-SRCH_IL.0,{len(loc_dash)}_KO{ko_s},{ko_e}.htm"

        return f"https://www.naukri.com/{kw_dash}-jobs-in-{loc_dash}"

    async def _handle_visual_tasks(self) -> bool:
        """Handle visual tasks like closing popups, accepting cookies, scrolling."""
        if not self.browser or not self.browser.page:
            return False

        try:
            # Close popups/banners using standard CSS selectors only
            await self.browser.page.evaluate("""() => {
                const closeSelectors = [
                    '[class*="close"]', '[class*="dismiss"]', '[class*="Cross"]',
                    '[class*="close-btn"]', '[class*="closeBtn"]', '[class*="close_button"]',
                    '[aria-label*="close"]', '[aria-label*="Close"]', '[aria-label*="dismiss"]',
                    'button[id*="close"]', 'button[id*="dismiss"]',
                    '.close-btn', '.dismiss-btn', '.modal-close', '.popup-close',
                    '[data-testid*="close"]', '[data-testid*="dismiss"]',
                    // LinkedIn sign-in modal
                    '[class*="sign-in"] button', '[class*="signin"] button',
                    '[class*="modal"] button[aria-label="Dismiss"]',
                    // Naukri location popup
                    '[class*="location"] button', '[class*="allow"]',
                    // General popups
                    '[class*="notification"] button', '[class*="popover"] button',
                    '[class*="banner"] button', '[class*="cookie"] button'
                ];
                for (const sel of closeSelectors) {
                    try {
                        const btns = document.querySelectorAll(sel);
                        btns.forEach(btn => {
                            if (btn.offsetParent !== null) {
                                const text = (btn.innerText || '').toLowerCase();
                                if (text.includes('close') || text.includes('dismiss') || text.includes('x') || text === '\u00d7' || text.includes('allow') || text.includes('ok') || text.includes('accept') || text.includes('not now')) {
                                    btn.click();
                                }
                            }
                        });
                    } catch(e) {}
                }

                // Accept cookies - use text content matching
                const allButtons = document.querySelectorAll('button, [role="button"], a[class*="btn"]');
                allButtons.forEach(btn => {
                    if (btn.offsetParent !== null) {
                        const text = (btn.innerText || '').trim().toLowerCase();
                        if (text.includes('accept') || text.includes('accept all') || text.includes('allow cookies') || text.includes('i agree') || text.includes('allow') || text.includes('not now')) {
                            btn.click();
                        }
                    }
                });
            }""")
            await self.browser.wait(1)

            # Scroll to load more content
            await self.browser.scroll("down", 800)
            await self.browser.wait(2)
            await self.browser.scroll("down", 800)
            await self.browser.wait(1)

            return True
        except Exception as e:
            self._log("ui_tars_visual", "warning", f"Visual tasks failed: {e}")
            return False

    async def _search_keyword(self, keyword: str, location: str, portal: str = "naukri", profile: Dict = None, experience_setting: str = "fresher") -> List[Dict]:
        """Execute search for one keyword on one portal."""
        is_fresher = (experience_setting == "fresher")
        url = self._build_search_url(keyword, location, portal)
        self._log(f"search_{portal}", "navigating", f"Searching '{keyword}' in {location}")
        self._log(f"search_{portal}", "url", url)

        try:
            await self.browser.go_to(url, timeout=30000)
            await self.browser.wait(4)

            # Debug: check page state
            try:
                page_title = await self.browser.page.title()
                page_url = await self.browser.get_url()
                self._log(f"search_{portal}", "debug", f"Page title: {page_title}, URL: {page_url}")
            except:
                pass

            # Handle visual tasks (popups, scrolling)
            await self._handle_visual_tasks()

            # Extract jobs
            jobs = await self.browser.extract_jobs()
            self._log(f"search_{portal}", "extracted", f"Raw extraction returned {len(jobs)} jobs")

            # Filter by experience if user is fresher
            # Use UI experience setting, not profile (profile may be wrong)
            is_fresher = profile.get("is_fresher", True)
            # Override with explicit UI setting
            # Experience filter logic
            exp_years = None
            
            if experience_setting == "fresher":
                exp_years = 0
            elif experience_setting == "experienced":
                exp_years = None  # No filtering
            else:
                try:
                    exp_years = int(experience_setting)
                except (ValueError, TypeError):
                    exp_years = 0
            
            filtered_jobs = []
            search_loc_lower = (location or "").lower()
            for job in jobs:
                exp = (job.get("experience_required", "") or "").lower()
                title = (job.get("title", "") or "").lower()
                job_location = (job.get("location", "") or "").lower()

                # Reject Indeed "Salary Search" entries (not real jobs)
                if "salary search" in title or "salary search" in (job.get("description", "") or "").lower():
                    continue

                # Reject jobs from wrong location (basic check)
                if job_location and search_loc_lower:
                    # Accept if location contains search term, or is empty/generic
                    if search_loc_lower not in job_location and job_location not in ["", "not specified", "india", "remote"]:
                        # Check for common city variants
                        city_aliases = {
                            "hyderabad": ["hyderabad", "secunderabad", "cyberabad", "hyd"],
                            "bangalore": ["bangalore", "bengaluru", "blr"],
                            "pune": ["pune", "pimpri", "hinjewadi"],
                            "chennai": ["chennai", "madras"],
                            "delhi": ["delhi", "new delhi", "ncr", "gurgaon", "noida"],
                            "mumbai": ["mumbai", "bombay", "thane"],
                        }
                        target_aliases = city_aliases.get(search_loc_lower, [search_loc_lower])
                        if not any(alias in job_location for alias in target_aliases):
                            continue

                # If user selected 0 years / fresher
                if exp_years == 0:
                    # 1. Reject if title contains seniority keywords or level indicators
                    senior_patterns = ["senior", "lead", "principal", "staff", "director", "manager", "architect", "head", "chief",
                                       " ii", " iii", " iv", " v", " l2", " l3", " l4", " l5", " l6",
                                       "-ii", "-iii", "-iv", "-2", "-3", "-4", "-5",
                                       " 2,", " 3,", " 4,", " 5,"]
                    if any(w in title for w in senior_patterns):
                        continue

                    # 2. Reject non-technical / spam / irrelevant jobs
                    spam_patterns = ["data entry", "work from home mobile", "typing job", "part time data",
                                     "back office", "computer operator", "data entry operator", "excel job",
                                     "legal", "business development", "marketing", "sales", "accountant",
                                     "hr executive", "recruitment", "content writer", "graphic designer"]
                    if any(w in title for w in spam_patterns):
                        continue

                    # 3. Check if title is tech-related (must have at least one tech keyword)
                    tech_keywords = ["software", "developer", "engineer", "programming", "coder", "tech", "backend", "frontend",
                                     "full stack", "fullstack", "web", "mobile", "app", "application", "java", "python", "react",
                                     "angular", "node", "devops", "cloud", "data", "analyst", "qa", "test", "automation",
                                     "database", "sql", "api", "microservice", "blockchain", "ai", "machine learning",
                                     "cyber", "security", "network", "system", "admin", "support", "technical"]
                    is_tech_job = any(w in title for w in tech_keywords) or any(w in (job.get("description", "") or "").lower()[:200] for w in tech_keywords)
                    if not is_tech_job:
                        continue

                    # 4. Check if title explicitly indicates fresher/intern/junior
                    is_fresher_title = any(w in title for w in ["fresher", "intern", "trainee", "graduate", "entry level", "junior", "apprentice", "0-1", "0-2", "sde-1", "sde 1", "software engineer i"])

                    # 5. Parse experience range
                    exp_match = re.search(r'(\d+)\s*[-–+]\s*(\d*)', exp)
                    if exp_match:
                        min_exp = int(exp_match.group(1))
                        # If min experience is greater than 0, reject unless title says fresher
                        if min_exp > 0:
                            if not is_fresher_title:
                                continue
                        # If min is 0, accept
                    elif any(w in exp for w in ["2+", "3+", "4+", "5+", "6+", "7+", "8+", "9+", "10+"]):
                         if not is_fresher_title:
                            continue
                    else:
                        # If experience is "Not specified" or empty, only allow if title indicates fresher
                        if not is_fresher_title:
                            continue

                # If user selected specific years (e.g., 2 years)
                elif exp_years is not None and exp_years > 0:
                    # Reject senior titles if user has low experience
                    if exp_years < 3 and any(w in title for w in ["senior", "lead", "principal", "staff", "director", "manager", "architect"]):
                        continue
                    
                    exp_match = re.search(r'(\d+)\s*[-–+]\s*(\d*)', exp)
                    if exp_match:
                        min_exp = int(exp_match.group(1))
                        # User with 2 years can apply for 0-2, 1-3, 2-5.
                        # User cannot apply for 3-5.
                        if exp_years < min_exp:
                            continue
                    elif any(w in exp for w in ["senior", "lead"]):
                        if exp_years < 3:
                             continue

                filtered_jobs.append(job)

            self._log(f"search_{portal}", "filtered", f"'{keyword}': {len(jobs)} raw → {len(filtered_jobs)} after experience filter")

            # Deduplicate
            new_jobs = []
            for job in filtered_jobs:
                url_key = job.get("source_url", "") or job.get("apply_url", "")
                if url_key and url_key not in self._seen_urls:
                    self._seen_urls.add(url_key)
                    new_jobs.append(job)
                elif not url_key:
                    title = job.get("title", "").lower()
                    company = job.get("company", "").lower()
                    combo_key = f"{title}|{company}"
                    if combo_key and combo_key not in self._seen_urls:
                        self._seen_urls.add(combo_key)
                        new_jobs.append(job)

            self._log(f"search_{portal}", "complete", f"'{keyword}': {len(filtered_jobs)} filtered, {len(new_jobs)} new after dedup")
            return new_jobs
        except Exception as e:
            self._log(f"search_{portal}", "error", f"'{keyword}' failed: {e}")
            return []

    async def _match_jobs_to_profile(self, raw_jobs: List[Dict], context: Dict) -> List[Dict]:
        """Step 3.5: Match raw jobs to user profile and score them."""
        profile = context.get("profile", {})
        user_skills = set(s.lower() for s in profile.get("skills", []))
        target_roles = [r.lower() for r in profile.get("target_roles", [])]
        is_fresher = profile.get("is_fresher", True)

        enriched = []
        for job in raw_jobs:
            title = (job.get("title", "") or "").lower()
            desc = (job.get("description", "") or "").lower()
            combined = title + " " + desc

            matched = [s for s in user_skills if s in combined]
            missing = [s for s in user_skills if s not in combined]

            # Base score starts at 0
            score = 0.0

            # Skill matching (up to 50 points)
            if user_skills and matched:
                skill_ratio = len(matched) / len(user_skills)
                score += skill_ratio * 50

            # Role matching (up to 20 points)
            role_matches = [role for role in target_roles if role in title]
            if role_matches:
                score += min(len(role_matches) * 10, 20)

            # Fresher-friendly bonus (10 points)
            exp_text = (job.get("experience_required", "") or "").lower()
            fresher_friendly = any(w in title + exp_text for w in ["fresher", "entry", "junior", "0-1", "0-2", "intern", "trainee"])
            if is_fresher and fresher_friendly:
                score += 10

            # Title relevance bonus (up to 20 points)
            title_keywords = ["developer", "engineer", "software", "programmer", "coder", "tech", "backend", "frontend", "full stack"]
            title_matches = sum(1 for kw in title_keywords if kw in title)
            score += min(title_matches * 5, 20)

            # Minimum score for any job that passed filters
            score = max(score, 10.0)

            enriched.append({
                **job,
                "match_score": min(round(score, 1), 100),
                "matched_skills": list(matched),
                "missing_skills": list(missing),
                "is_fresher_friendly": fresher_friendly,
                "should_apply": score >= 50,
            })

        enriched.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return enriched

    async def _save_jobs(self, matched_jobs: List[Dict], context: Dict) -> Dict:
        """Save matched jobs to database."""
        if not matched_jobs:
            return {"new": 0, "duplicates": 0, "skipped": 0}

        from agents.job_saver import JobSaver

        profile = context.get("profile", {})
        resume_text = context.get("resume_text", "")
        is_fresher = profile.get("is_fresher", True)
        skills = profile.get("skills", [])

        jobs_to_save = []
        for job in matched_jobs:
            entry = {
                "title": job.get("title", ""),
                "company": job.get("company", "Unknown"),
                "location": job.get("location", "Not specified"),
                "source": job.get("source", "web"),
                "source_url": job.get("source_url", ""),
                "apply_url": job.get("apply_url", ""),
                "salary": job.get("salary", "Not specified"),
                "description": job.get("description", ""),
                "experience_required": job.get("experience_required", "Not specified"),
                "posted_text": job.get("posted_text", ""),
            }
            # Pass posted_date if already parsed by autonomous agent
            if job.get("posted_date"):
                entry["posted_date"] = job["posted_date"]
            jobs_to_save.append(entry)

        saver = JobSaver()
        result = await saver.save_jobs(
            jobs_to_save,
            resume_text,
            user_id=context.get("user_id"),
            is_fresher=is_fresher,
            skills=skills,
        )

        self._log("job_saver", "complete", f"Saved {result['new']} new, {result['duplicates']} duplicates, {result.get('skipped', 0)} skipped")
        return result

    async def run_search(self, user_request: str, context: Dict) -> Dict:
        """Execute job search using autonomous agent with vision."""
        self._tool_log = []
        self._seen_urls = set()
        self._used_keywords = set()

        profile = context.get("profile", {})
        target_count = context.get("target_count", 20)
        location = context.get("location", "Hyderabad")
        selected_portals = context.get("portals", None)

        # Ensure target_count is an integer from UI
        try:
            target_count = int(target_count) if target_count else 20
        except (ValueError, TypeError):
            target_count = 20

        # ─── Generate keywords using AI ──────────────────────────────────
        form_keywords = context.get("keywords", "")

        # Parse keywords from form
        if form_keywords and isinstance(form_keywords, str):
            user_keywords = [k.strip() for k in form_keywords.split(",") if k.strip()]
        elif form_keywords and isinstance(form_keywords, list):
            user_keywords = form_keywords
        else:
            user_keywords = []

        # Form experience setting overrides resume analysis for keyword generation
        ui_exp = context.get("experience", "").strip().lower()
        if ui_exp == "fresher":
            profile["is_fresher"] = True
        elif ui_exp == "experienced":
            profile["is_fresher"] = False
        elif ui_exp.isdigit():
            profile["is_fresher"] = int(ui_exp) <= 2
        # else: keep the resume analysis value

        # Use AI to generate smart keywords
        keywords = await self._generate_keywords_with_ai(profile, user_keywords, location)

        self._log("brain_planning", "keywords", f"Generated {len(keywords)} keywords: {', '.join(keywords[:5])}")

        # ─── Determine portals to search ────────────────────────────────
        # Glassdoor disabled — Cloudflare IP-blocks automated access
        all_portals = ["naukri", "indeed", "linkedin", "timesjobs", "shine", "foundit", "cutshort"]
        if selected_portals:
            portal_order = [p for p in selected_portals if p in all_portals]
            if not portal_order:
                portal_order = all_portals
        else:
            portal_order = all_portals

        self._log("brain_planning", "portals", f"Searching on: {', '.join(portal_order)}")

        # ─── Use Autonomous Agent for search ─────────────────────────────
        from agents.browser_agent.autonomous_agent import AutonomousAgent

        self._log("browser_init", "starting", "Starting autonomous agent...")
        agent = AutonomousAgent(headless=False)
        all_raw_jobs = []

        try:
            # Combine keywords for the agent — use ALL generated keywords, not truncated
            search_keywords = ", ".join(keywords)

            # Run autonomous search — per-portal timeouts are handled inside run_task()
            # Form experience setting overrides resume analysis
            ui_exp = context.get("experience", "").strip().lower()
            if ui_exp == "fresher":
                is_fresher = True
            elif ui_exp == "experienced":
                is_fresher = False
            elif ui_exp.isdigit():
                is_fresher = int(ui_exp) <= 2
            else:
                is_fresher = profile.get("is_fresher", True)

            all_raw_jobs = await agent.run_task(
                task=f"Search for jobs matching: {search_keywords}",
                target_count=target_count,
                keywords=search_keywords,
                is_fresher=is_fresher,
                location=location,
                portals=portal_order,
                overall_timeout=900,  # 15 minute overall budget (multiple keyword rounds)
            )

            self._log("agent_search", "complete", f"Autonomous agent found {len(all_raw_jobs)} jobs")
            round_num = len(portal_order)

        except Exception as e:
            self._log("agent_search", "error", f"Autonomous agent failed: {type(e).__name__}: {e}")
            all_raw_jobs = []
            round_num = 0
        finally:
            # Always clean up browser between searches
            try:
                if agent.browser and agent.browser.browser:
                    await agent.browser.close()
            except:
                pass

        self._log("search_complete", "done", f"Total raw jobs: {len(all_raw_jobs)}")

        # ─── Match & Score (Brain) ──────────────────────────────────────
        if all_raw_jobs:
            self._log("brain_matching", "starting", f"Analyzing {len(all_raw_jobs)} jobs against profile...")
            matched_jobs = await self._match_jobs_to_profile(all_raw_jobs, context)
            self._log("brain_matching", "complete", f"Matched and scored {len(matched_jobs)} jobs")
        else:
            matched_jobs = []
            self._log("brain_matching", "complete", "No jobs found to match")

        # ─── Save to DB ─────────────────────────────────────────────────
        if matched_jobs:
            self._log("job_saver", "starting", "Saving matched jobs to database...")
            try:
                await self._save_jobs(matched_jobs, context)
            except Exception as e:
                self._log("job_saver", "error", str(e))

        # ─── Format Response ────────────────────────────────────────────
        search_keywords = ", ".join(list(self._used_keywords)[:2]) if self._used_keywords else "jobs"

        if not matched_jobs:
            return {
                "response": f"I searched across {round_num} rounds for {search_keywords} in {location} but couldn't find any listings. Try different keywords.",
                "tool_uses": self._tool_log,
                "jobs": [],
            }

        profile_info = ""
        if profile:
            profile_info = (
                f"**Your Profile:** {profile.get('name', 'You')} | "
                f"Skills: {', '.join(profile.get('skills', [])[:5])} | "
                f"Roles: {', '.join(profile.get('target_roles', [])[:3])}\n\n"
            )

        response = f"Found {len(matched_jobs)} {search_keywords} jobs in {location} (searched {round_num} rounds):\n\n{profile_info}"

        for i, job in enumerate(matched_jobs[:15], 1):
            score = job.get("match_score", 0)
            score_icon = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
            response += f"{i}. {score_icon} **{job.get('title', 'N/A')}** at {job.get('company', 'N/A')} - {job.get('location', 'N/A')}\n"
            response += f"   Match: {score:.0f}%"
            exp = job.get("experience_required", "")
            if exp and exp != "Not specified":
                response += f" | Experience: {exp}"
            response += "\n"
            if job.get("matched_skills"):
                response += f"   Matched: {', '.join(job['matched_skills'][:4])}\n"
            if job.get("description"):
                desc = job["description"][:120]
                response += f"   {desc}{'...' if len(job['description']) > 120 else ''}\n"
            response += "\n"

        if len(matched_jobs) > 15:
            response += f"...and {len(matched_jobs) - 15} more jobs saved to your dashboard.\n\n"

        response += "All jobs are saved with match scores. View them at http://localhost:8001/dashboard"

        return {
            "response": response,
            "tool_uses": self._tool_log,
            "jobs": matched_jobs,
        }

    async def cleanup(self):
        """Clean up resources."""
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None
