"""
Company Intelligence Agent - Deep research on companies

For each job found, this agent:
1. Researches the company (size, funding, tech stack, culture)
2. Finds recent news and growth signals
3. Identifies key people (HR, tech leads, founders)
4. Generates personalized outreach angles
"""

import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CompanyProfile:
    """Deep profile of a company"""
    name: str
    website: str = ""
    linkedin_url: str = ""
    glassdoor_url: str = ""
    
    # Basic info
    industry: str = ""
    size: str = ""  # "1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"
    founded: str = ""
    headquarters: str = ""
    description: str = ""
    
    # Tech stack
    tech_stack: List[str] = field(default_factory=list)
    programming_languages: List[str] = field(default_factory=list)
    
    # Funding (for startups)
    total_funding: str = ""
    last_funding_round: str = ""
    investors: List[str] = field(default_factory=list)
    
    # Culture signals
    glassdoor_rating: float = 0.0
    glassdoor_reviews: int = 0
    work_life_balance: str = ""
    culture_rating: str = ""
    
    # Recent news
    recent_news: List[Dict] = field(default_factory=list)
    growth_signals: List[str] = field(default_factory=list)
    
    # People to reach out to
    hr_contacts: List[Dict] = field(default_factory=list)
    tech_leads: List[Dict] = field(default_factory=list)
    founders: List[Dict] = field(default_factory=list)
    
    # Outreach angles
    outreach_angles: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "website": self.website,
            "linkedin_url": self.linkedin_url,
            "industry": self.industry,
            "size": self.size,
            "founded": self.founded,
            "headquarters": self.headquarters,
            "description": self.description[:500] if self.description else "",
            "tech_stack": self.tech_stack,
            "programming_languages": self.programming_languages,
            "total_funding": self.total_funding,
            "glassdoor_rating": self.glassdoor_rating,
            "growth_signals": self.growth_signals,
            "outreach_angles": self.outreach_angles,
            "hr_contacts": self.hr_contacts[:3],  # Limit for privacy
            "tech_leads": self.tech_leads[:3],
        }


class CompanyResearchAgent:
    """Researches companies deeply using AI and web data"""
    
    def __init__(self):
        from ai.ai_client import get_ai_client
        self.ai = get_ai_client()
    
    async def research_company(self, company_name: str, job_context: Dict = None) -> CompanyProfile:
        """Deep research on a company"""
        logger.info(f"Researching company: {company_name}")
        
        profile = CompanyProfile(name=company_name)
        
        try:
            # Step 1: AI-powered company research
            ai_research = await self._ai_company_research(company_name, job_context)
            profile = self._merge_ai_research(profile, ai_research)
            
            # Step 2: Find tech stack
            profile.tech_stack = await self._find_tech_stack(company_name)
            
            # Step 3: Generate outreach angles
            profile.outreach_angles = await self._generate_outreach_angles(
                company_name, profile, job_context
            )
            
        except Exception as e:
            logger.error(f"Error researching {company_name}: {e}")
        
        return profile
    
    async def _ai_company_research(self, company_name: str, job_context: Dict = None) -> Dict:
        """Use AI to research a company"""
        
        job_info = ""
        if job_context:
            job_info = f"""
Job Context:
- Title: {job_context.get('title', 'N/A')}
- Skills Required: {', '.join(job_context.get('skills_required', []))}
- Description: {job_context.get('description', 'N/A')[:300]}
"""
        
        prompt = f"""Research the company "{company_name}" and provide detailed intelligence.

{job_info}

Return a JSON object with:
{{
    "website": "company website URL",
    "linkedin_url": "LinkedIn company page URL",
    "industry": "industry/sector",
    "size": "company size (1-10, 11-50, 51-200, 201-500, 501-1000, 1000+)",
    "founded": "year founded",
    "headquarters": "city, country",
    "description": "brief company description",
    "tech_stack": ["technologies used"],
    "programming_languages": ["languages used"],
    "total_funding": "funding amount if startup",
    "glassdoor_rating": 4.0,
    "work_life_balance": "good/average/poor",
    "growth_signals": ["recent achievements, funding, hiring spree, etc"],
    "recent_news": [{{"title": "news title", "date": "2024", "summary": "brief summary"}}],
    "hr_contacts": [{{"name": "Name", "title": "HR/Recruiter", "linkedin": "profile url"}}],
    "tech_leads": [{{"name": "Name", "title": "Tech Lead/Manager", "linkedin": "profile url"}}],
    "founders": [{{"name": "Name", "title": "Founder/CEO", "linkedin": "profile url"}}]
}}

Be thorough. Use your knowledge of Indian tech companies. If you're unsure about specific data, make reasonable estimates based on the company's industry and size.
Return ONLY valid JSON."""

        try:
            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a company research analyst. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                json_mode=True,
            )
            
            return json.loads(response)
            
        except Exception as e:
            logger.error(f"AI research failed for {company_name}: {e}")
            return {}
    
    def _merge_ai_research(self, profile: CompanyProfile, research: Dict) -> CompanyProfile:
        """Merge AI research into profile"""
        profile.website = research.get("website", "")
        profile.linkedin_url = research.get("linkedin_url", "")
        profile.industry = research.get("industry", "")
        profile.size = research.get("size", "")
        profile.founded = research.get("founded", "")
        profile.headquarters = research.get("headquarters", "")
        profile.description = research.get("description", "")
        profile.tech_stack = research.get("tech_stack", [])
        profile.programming_languages = research.get("programming_languages", [])
        profile.total_funding = research.get("total_funding", "")
        profile.glassdoor_rating = research.get("glassdoor_rating", 0)
        profile.work_life_balance = research.get("work_life_balance", "")
        profile.growth_signals = research.get("growth_signals", [])
        profile.recent_news = research.get("recent_news", [])
        profile.hr_contacts = research.get("hr_contacts", [])
        profile.tech_leads = research.get("tech_leads", [])
        profile.founders = research.get("founders", [])
        return profile
    
    async def _find_tech_stack(self, company_name: str) -> List[str]:
        """Find technologies used by the company"""
        prompt = f"""What technologies does "{company_name}" use? 
List the main technologies, frameworks, and tools.
Return ONLY a JSON array of strings, e.g.: ["Python", "Django", "PostgreSQL", "AWS"]
Be concise, max 15 items."""

        try:
            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=300,
            )
            
            # Parse JSON array
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
                
        except Exception as e:
            logger.error(f"Tech stack lookup failed: {e}")
        
        return []
    
    async def _generate_outreach_angles(
        self, company_name: str, profile: CompanyProfile, job_context: Dict = None
    ) -> List[str]:
        """Generate personalized outreach angles"""
        
        job_info = ""
        if job_context:
            job_info = f"""
Job Title: {job_context.get('title', 'N/A')}
Skills: {', '.join(job_context.get('skills_required', []))}
"""
        
        prompt = f"""Generate 3-5 personalized outreach angles for reaching out to people at "{company_name}".

Company Info:
- Industry: {profile.industry}
- Size: {profile.size}
- Tech Stack: {', '.join(profile.tech_stack[:5]) if profile.tech_stack else 'Unknown'}
- Recent News: {json.dumps(profile.recent_news[:2]) if profile.recent_news else 'None'}
- Growth Signals: {', '.join(profile.growth_signals[:3]) if profile.growth_signals else 'None'}
{job_info}

Each angle should be a specific, personalized reason to reach out. Examples:
- "I noticed {company_name} just raised Series A - I'd love to contribute to the growth"
- "Your tech stack uses Python/Django which matches my experience"
- "I saw your recent product launch on TechCrunch"

Return ONLY a JSON array of strings."""

        try:
            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=500,
            )
            
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
                
        except Exception as e:
            logger.error(f"Outreach angle generation failed: {e}")
        
        return []


# Singleton
company_researcher = CompanyResearchAgent()
