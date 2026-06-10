"""Resume analyzer - AI-first approach."""
import re
from typing import Dict, List, Any
from ai.ai_client import get_ai_client


class ResumeAnalyzer:
    """Analyzes resume using AI to extract structured data."""

    async def analyze(self, resume_text: str) -> Dict:
        """AI-powered resume analysis."""
        if not resume_text or len(resume_text.strip()) < 50:
            return self._default_profile()

        # Try AI analysis first
        ai_data = await self._ai_analyze(resume_text)
        # Check if we got valid skills (not None, not empty if we have enough text)
        skills = ai_data.get("skills") if ai_data else None
        if skills:
            return ai_data

        # Fallback to basic extraction if AI failed or returned no skills
        return self._basic_extract(resume_text)

    async def _ai_analyze(self, text: str) -> Dict:
        """AI-powered deep analysis."""
        try:
            ai = get_ai_client()
            prompt = f"""Analyze this resume and return ONLY valid JSON (no markdown, no backticks):

{text[:3000]}

Return JSON with these fields:
{{
  "name": "full name",
  "email": "email from resume",
  "phone": "phone from resume",
  "skills": ["list of top 10 technical skills"],
  "experience_years": 0,
  "is_fresher": true,
  "education": "degree and university",
  "target_roles": ["3-5 suitable job roles for this person"],
  "preferred_locations": ["preferred work locations"],
  "summary": "2-line professional summary",
  "strengths": ["3 key strengths"],
  "improvements": ["3 suggestions to improve resume"]
}}

IMPORTANT RULES:
- is_fresher MUST be TRUE if: person has ONLY internships (not full-time jobs), graduated recently (2020-2026), or has < 1 year of full-time (non-internship) work experience
- Internships do NOT count as full-time experience. An "Appian Consultant Intern" is still a fresher.
- is_fresher should be FALSE ONLY if: person has 1+ years of confirmed full-time (non-internship, non-contract) work experience with clear dates
- experience_years should be 0 for freshers/interns, otherwise actual years of full-time work
- target_roles should match the person's ACTUAL skills and experience level (junior/entry-level roles for freshers)
- skills should be the most relevant technical skills found in the resume"""

            response = await ai.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            if not response or not response.strip():
                print("AI returned empty response, falling back to basic extract")
                return {}

            # Clean response - handle various formats
            response = response.strip()

            # Remove markdown code blocks
            if '```' in response:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
                if match:
                    response = match.group(1).strip()

            # Try to extract JSON if response has extra text
            import json
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                response = json_match.group()

            data = json.loads(response)

            # Validate and ensure required fields
            return {
                "name": data.get("name", "Unknown"),
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "skills": data.get("skills", []),
                "experience_years": float(data.get("experience_years", 0)),
                "is_fresher": bool(data.get("is_fresher", True)),
                "education": data.get("education", ""),
                "target_roles": data.get("target_roles", []),
                "preferred_locations": data.get("preferred_locations", ["Hyderabad"]),
                "summary": data.get("summary", ""),
                "strengths": data.get("strengths", []),
                "improvements": data.get("improvements", []),
            }
        except Exception as e:
            import traceback
            print(f"AI analysis failed: {e}")
            traceback.print_exc()
            return {}

    def _basic_extract(self, text: str) -> Dict:
        """Basic regex extraction as fallback."""
        text_lower = text.lower()

        # Email
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        email = email_match.group(0) if email_match else ""

        # Phone
        phone_match = re.search(r'[\+]?[\d\s\-\(\)]{10,15}', text)
        phone = phone_match.group(0).strip() if phone_match else ""

        # Name (first line)
        lines = text.strip().split('\n')
        name = lines[0].strip()[:50] if lines else "Unknown"

        # Basic skill extraction
        skill_keywords = ["java", "python", "sql", "javascript", "react", "angular", "html", "css",
                         "node", "aws", "docker", "git", "appian", "spring", "django", "fastapi"]
        skills = [s for s in skill_keywords if s in text_lower][:10]

        # Fresher detection - simple heuristic
        is_fresher = any(w in text_lower for w in ["fresher", "intern", "trainee", "graduate", "entry level"])
        if not is_fresher:
            # Check for recent graduation
            grad_match = re.search(r'20[2-2][0-9]', text)
            if grad_match:
                grad_year = int(grad_match.group(0))
                if grad_year >= 2023:
                    is_fresher = True

        return {
            "name": name,
            "email": email,
            "phone": phone,
            "skills": skills,
            "experience_years": 0 if is_fresher else 2,
            "is_fresher": is_fresher,
            "education": "",
            "target_roles": ["Software Developer", "Junior Developer"],
            "preferred_locations": ["Hyderabad"],
            "summary": "",
            "strengths": [],
            "improvements": [],
        }

    def _default_profile(self) -> Dict:
        """Default profile for empty/invalid resumes."""
        return {
            "name": "User",
            "email": "",
            "phone": "",
            "skills": ["Java", "Python", "SQL"],
            "experience_years": 0,
            "is_fresher": True,
            "education": "",
            "target_roles": ["Software Developer"],
            "preferred_locations": ["Hyderabad"],
            "summary": "",
            "strengths": [],
            "improvements": [],
        }
