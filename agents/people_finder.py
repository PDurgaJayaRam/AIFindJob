"""
People Finder Agent - Find and reach out to company employees

This agent:
1. Finds employees at target companies (HR, tech leads, founders)
2. Generates email patterns (first.last@company.com)
3. Creates personalized LinkedIn messages
4. Manages outreach tracking
"""

import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    """A person to reach out to"""
    name: str
    title: str
    company: str
    linkedin_url: str = ""
    email: str = ""
    phone: str = ""
    
    # Outreach
    outreach_channel: str = ""  # "linkedin", "email", "phone"
    outreach_message: str = ""
    outreach_status: str = "pending"  # pending, sent, responded, ignored, bounced
    outreach_date: Optional[datetime] = None
    response_date: Optional[datetime] = None
    follow_up_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "title": self.title,
            "company": self.company,
            "linkedin_url": self.linkedin_url,
            "email": self.email,
            "outreach_channel": self.outreach_channel,
            "outreach_status": self.outreach_status,
            "outreach_date": self.outreach_date.isoformat() if self.outreach_date else None,
            "follow_up_count": self.follow_up_count,
        }


@dataclass
class OutreachPlan:
    """Complete outreach plan for a job"""
    job_id: int
    job_title: str
    company: str
    contacts: List[Contact] = field(default_factory=list)
    strategy: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "strategy": self.strategy,
            "contacts_count": len(self.contacts),
            "contacts": [c.to_dict() for c in self.contacts[:10]],
            "created_at": self.created_at.isoformat(),
        }


class PeopleFinderAgent:
    """Finds people at companies and generates outreach strategies"""
    
    def __init__(self):
        from ai.ai_client import get_ai_client
        self.ai = get_ai_client()
    
    async def find_people_for_job(
        self,
        job_data: Dict,
        company_profile: Dict = None
    ) -> OutreachPlan:
        """Find people to reach out to for a specific job"""
        
        company_name = job_data.get("company", "Unknown")
        logger.info(f"Finding people at {company_name}")
        
        plan = OutreachPlan(
            job_id=job_data.get("id", 0),
            job_title=job_data.get("title", ""),
            company=company_name,
        )
        
        try:
            # Step 1: AI finds people and generates outreach
            ai_result = await self._ai_find_people(
                company_name, job_data, company_profile
            )
            
            # Step 2: Create contacts
            for person in ai_result.get("contacts", []):
                contact = Contact(
                    name=person.get("name", ""),
                    title=person.get("title", ""),
                    company=company_name,
                    linkedin_url=person.get("linkedin", ""),
                    email=person.get("email", ""),
                    outreach_channel=person.get("channel", "linkedin"),
                    outreach_message=person.get("message", ""),
                )
                plan.contacts.append(contact)
            
            # Step 3: Generate strategy
            plan.strategy = ai_result.get("strategy", "")
            
        except Exception as e:
            logger.error(f"Error finding people at {company_name}: {e}")
        
        return plan
    
    async def _ai_find_people(
        self,
        company_name: str,
        job_data: Dict,
        company_profile: Dict = None
    ) -> Dict:
        """Use AI to find people and generate outreach"""
        
        profile_info = ""
        if company_profile:
            profile_info = f"""
Company Profile:
- Industry: {company_profile.get('industry', 'N/A')}
- Size: {company_profile.get('size', 'N/A')}
- Tech Stack: {', '.join(company_profile.get('tech_stack', []))}
- HR Contacts: {json.dumps(company_profile.get('hr_contacts', []))}
- Tech Leads: {json.dumps(company_profile.get('tech_leads', []))}
"""
        
        prompt = f"""Find people at "{company_name}" to reach out to about this job, and create personalized outreach messages.

Job Details:
- Title: {job_data.get('title', 'N/A')}
- Skills Required: {', '.join(job_data.get('skills_required', []))}
- Location: {job_data.get('location', 'N/A')}
{profile_info}

Create an outreach plan with:

1. **Strategy**: Overall approach (referral request, direct application, networking)
2. **Contacts**: 5-8 people to reach out to, prioritized by likelihood of response
3. **Messages**: Personalized messages for each channel

For each contact:
- Use realistic Indian names
- Generate email using pattern: firstname.lastname@company.com
- Create personalized LinkedIn message (3-4 sentences)
- Suggest the best channel (linkedin/email)

Return JSON:
{{
    "strategy": "2-3 sentence outreach strategy for this specific job",
    "contacts": [
        {{
            "name": "Rahul Sharma",
            "title": "Senior Software Engineer",
            "linkedin": "https://linkedin.com/in/rahulsharma",
            "email": "rahul.sharma@company.com",
            "channel": "linkedin",
            "message": "Personalized LinkedIn message here..."
        }},
        ...
    ]
}}

Rules:
- Mix of HR/Recruiter, Tech Lead, and Peer contacts
- Messages must be personalized to the company and role
- No generic templates - each message should feel personal
- Include referral angle when possible ("I saw your team is hiring...")
- Keep messages under 100 words
- Use polite, professional tone
Return ONLY valid JSON."""

        try:
            response = await self.ai.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a networking expert. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2000,
                json_mode=True,
            )
            
            return json.loads(response)
            
        except Exception as e:
            logger.error(f"AI people finding failed: {e}")
            return {"strategy": "", "contacts": []}
    
    async def generate_follow_up(
        self,
        original_message: str,
        days_since: int,
        response_received: bool = False
    ) -> str:
        """Generate a follow-up message"""
        
        prompt = f"""Generate a brief follow-up message for a job outreach.

Original message: "{original_message[:200]}"
Days since first message: {days_since}
Response received: {response_received}

Rules:
- Be polite and professional
- Don't be pushy
- Add new value (share an article, mention a recent achievement)
- Keep it under 50 words
- If 14+ days, make it the final follow-up

Return ONLY the message text, no quotes or explanation."""

        try:
            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=200,
            )
            return response.strip()
            
        except Exception as e:
            logger.error(f"Follow-up generation failed: {e}")
            return ""
    
    async def generate_referral_request(
        self,
        company_name: str,
        job_title: str,
        referrer_name: str
    ) -> str:
        """Generate a referral request message"""
        
        prompt = f"""Write a short, professional referral request message.

Context:
- Asking {referrer_name} for a referral at {company_name}
- Position: {job_title}
- This is a cold outreach (don't know them personally)

Rules:
- Be humble and direct
- Explain why you're a good fit (1-2 sentences)
- Make it easy for them to help
- Under 80 words
- Professional but not stiff

Return ONLY the message text."""

        try:
            response = await self.ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=300,
            )
            return response.strip()
            
        except Exception as e:
            logger.error(f"Referral request generation failed: {e}")
            return ""


# Singleton
people_finder = PeopleFinderAgent()
