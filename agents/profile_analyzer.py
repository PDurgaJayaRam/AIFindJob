"""Profile Analyzer Agent - Parse resumes, extract skills, and provide recommendations.

Features:
- Resume parsing (PDF, DOCX, TXT)
- Skill extraction and categorization
- Experience level detection
- Gap analysis against target roles
- Career path recommendations
"""
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


# ─── Skill Categories ─────────────────────────────────────────────────────────
SKILL_CATEGORIES = {
    "programming_languages": [
        "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "go",
        "rust", "kotlin", "swift", "scala", "php", "perl", "r", "matlab",
        "sql", "html", "css", "sass", "less"
    ],
    "frameworks": [
        "react", "angular", "vue", "vue.js", "next.js", "nuxt", "svelte",
        "node.js", "express", "django", "flask", "fastapi", "spring", "spring boot",
        "asp.net", ".net core", "rails", "laravel", "symfony",
        "flutter", "react native", "ionic"
    ],
    "databases": [
        "mysql", "postgresql", "mongodb", "redis", "elasticsearch", "cassandra",
        "oracle", "sql server", "sqlite", "dynamodb", "firebase", "neo4j"
    ],
    "cloud_platforms": [
        "aws", "azure", "gcp", "google cloud", "heroku", "digitalocean",
        "firebase", "vercel", "netlify"
    ],
    "devops_tools": [
        "docker", "kubernetes", "jenkins", "git", "github", "gitlab",
        "ci/cd", "terraform", "ansible", "puppet", "chef", "circleci",
        "travis ci", "github actions"
    ],
    "data_science": [
        "machine learning", "deep learning", "tensorflow", "pytorch", "keras",
        "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn",
        "data analysis", "data visualization", "nlp", "computer vision",
        "neural networks", "ai", "artificial intelligence"
    ],
    "soft_skills": [
        "communication", "teamwork", "leadership", "problem solving",
        "critical thinking", "time management", "adaptability", "creativity"
    ]
}

# ─── Experience Keywords ──────────────────────────────────────────────────────
EXPERIENCE_PATTERNS = {
    "fresher": [
        "fresher", "fresh graduate", "recent graduate", "entry level",
        "0-1 years", "0-2 years", "0 years", "no experience",
        "campus hire", "graduate trainee"
    ],
    "junior": [
        "junior", "associate", "trainee", "intern", "apprentice",
        "1-3 years", "2-3 years", "1-2 years"
    ],
    "mid": [
        "mid level", "software engineer", "developer",
        "3-5 years", "4-6 years", "5+ years"
    ],
    "senior": [
        "senior", "lead", "principal", "staff", "architect",
        "7+ years", "8+ years", "10+ years"
    ]
}


@dataclass
class ProfileAnalysis:
    """Result of profile analysis."""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    
    # Skills
    skills: List[str] = field(default_factory=list)
    skill_categories: Dict[str, List[str]] = field(default_factory=dict)
    
    # Experience
    experience_years: float = 0
    experience_level: str = "fresher"  # fresher, junior, mid, senior
    companies: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    
    # Education
    education: List[Dict] = field(default_factory=list)
    
    # Recommendations
    target_roles: List[str] = field(default_factory=list)
    skill_gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Raw text
    raw_text: str = ""
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "skills": self.skills,
            "skill_categories": self.skill_categories,
            "experience_years": self.experience_years,
            "experience_level": self.experience_level,
            "companies": self.companies,
            "roles": self.roles,
            "education": self.education,
            "target_roles": self.target_roles,
            "skill_gaps": self.skill_gaps,
            "recommendations": self.recommendations,
        }


class ProfileAnalyzer:
    """Analyze user profiles and resumes."""
    
    def __init__(self):
        self.all_skills = set()
        for category_skills in SKILL_CATEGORIES.values():
            self.all_skills.update(category_skills)
    
    def analyze_resume(self, resume_text: str, target_role: str = None) -> ProfileAnalysis:
        """Analyze resume text and extract profile information."""
        analysis = ProfileAnalysis(raw_text=resume_text)
        
        # Extract contact info
        analysis.email = self._extract_email(resume_text)
        analysis.phone = self._extract_phone(resume_text)
        analysis.location = self._extract_location(resume_text)
        analysis.name = self._extract_name(resume_text)
        
        # Extract skills
        analysis.skills = self._extract_skills(resume_text)
        analysis.skill_categories = self._categorize_skills(analysis.skills)
        
        # Extract experience
        exp_info = self._extract_experience(resume_text)
        analysis.experience_years = exp_info["years"]
        analysis.experience_level = exp_info["level"]
        analysis.companies = exp_info["companies"]
        analysis.roles = exp_info["roles"]
        
        # Extract education
        analysis.education = self._extract_education(resume_text)
        
        # Generate recommendations
        if target_role:
            analysis.target_roles = [target_role]
            analysis.skill_gaps = self._analyze_gaps(analysis, target_role)
            analysis.recommendations = self._generate_recommendations(analysis, target_role)
        
        return analysis
    
    def _extract_email(self, text: str) -> str:
        """Extract email address from text."""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(pattern, text)
        return match.group(0) if match else ""
    
    def _extract_phone(self, text: str) -> str:
        """Extract phone number from text."""
        # Indian phone numbers
        patterns = [
            r'\+91[\s-]?\d{10}',
            r'\d{10}',
            r'\d{5}[\s-]\d{5}',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return ""
    
    def _extract_location(self, text: str) -> str:
        """Extract location from text."""
        # Common Indian cities
        cities = [
            "bangalore", "bengaluru", "mumbai", "pune", "hyderabad",
            "chennai", "delhi", "noida", "gurgaon", "kolkata",
            "ahmedabad", "jaipur", "lucknow", "kochi", "coimbatore"
        ]
        
        text_lower = text.lower()
        for city in cities:
            if city in text_lower:
                return city.title()
        
        return ""
    
    def _extract_name(self, text: str) -> str:
        """Extract name from resume (usually first line)."""
        lines = text.strip().split('\n')
        for line in lines[:5]:
            line = line.strip()
            # Skip empty lines, email, phone, etc.
            if not line or '@' in line or re.search(r'\d{10}', line):
                continue
            # Name is usually 2-4 words, capitalized
            words = line.split()
            if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                return line
        return ""
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from text."""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.all_skills:
            # Use word boundary matching for better accuracy
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)
        
        return list(set(found_skills))
    
    def _categorize_skills(self, skills: List[str]) -> Dict[str, List[str]]:
        """Categorize skills into categories."""
        categories = {}
        
        for category, category_skills in SKILL_CATEGORIES.items():
            matched = [s for s in skills if s in category_skills]
            if matched:
                categories[category] = matched
        
        return categories
    
    def _extract_experience(self, text: str) -> Dict:
        """Extract experience information."""
        text_lower = text.lower()
        
        # Extract years of experience
        years = 0
        patterns = [
            r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)',
            r'experience\s*:\s*(\d+)\+?\s*(?:years?|yrs?)',
            r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:in|of)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                years = int(match.group(1))
                break
        
        # Determine level
        level = "fresher"
        if years >= 7:
            level = "senior"
        elif years >= 3:
            level = "mid"
        elif years >= 1:
            level = "junior"
        
        # Check for experience keywords
        for exp_level, keywords in EXPERIENCE_PATTERNS.items():
            if any(kw in text_lower for kw in keywords):
                level = exp_level
                break
        
        # Extract companies
        companies = []
        company_patterns = [
            r'(?:at|@)\s+([A-Z][a-zA-Z\s&]+?)(?:\s*,|\s*\(|\s*$)',
            r'([A-Z][a-zA-Z\s&]+?)\s*(?:Private Limited|Ltd|Inc|Corp)',
        ]
        for pattern in company_patterns:
            matches = re.findall(pattern, text)
            companies.extend([m.strip() for m in matches if len(m.strip()) > 2])
        
        # Extract roles
        roles = []
        role_keywords = [
            "developer", "engineer", "intern", "analyst", "consultant",
            "manager", "lead", "architect", "designer", "tester"
        ]
        for line in text.split('\n'):
            line_lower = line.lower().strip()
            if any(kw in line_lower for kw in role_keywords):
                # Extract role title
                words = line.split()
                for i, word in enumerate(words):
                    if word.lower() in role_keywords:
                        role = ' '.join(words[max(0, i-2):i+1])
                        roles.append(role.strip())
                        break
        
        return {
            "years": years,
            "level": level,
            "companies": list(set(companies))[:5],
            "roles": list(set(roles))[:5],
        }
    
    def _extract_education(self, text: str) -> List[Dict]:
        """Extract education information."""
        education = []
        
        # Degree patterns
        degree_patterns = [
            r'(B\.?Tech|Bachelor(?:\'s)?\s*(?:of\s*)?(?:Technology|Engineering|Science|Arts|Commerce))',
            r'(M\.?Tech|Master(?:\'s)?\s*(?:of\s*)?(?:Technology|Engineering|Science|Arts|Commerce))',
            r'(B\.?C\.?A|Bachelor(?:\'s)?\s*(?:of\s*)?Computer\s*Applications)',
            r'(M\.?C\.?A|Master(?:\'s)?\s*(?:of\s*)?Computer\s*Applications)',
            r'(B\.?S\.?C|Bachelor(?:\'s)?\s*(?:of\s*)?Science)',
            r'(M\.?S\.?C|Master(?:\'s)?\s*(?:of\s*)?Science)',
            r'(B\.?E\.?|Bachelor(?:\'s)?\s*(?:of\s*)?Engineering)',
            r'(M\.?E\.?|Master(?:\'s)?\s*(?:of\s*)?Engineering)',
            r'(Ph\.?D|Doctor(?:\'s)?\s*(?:of\s*)?Philosophy)',
            r'(MBA|Master(?:\'s)?\s*(?:of\s*)?Business\s*Administration)',
        ]
        
        for pattern in degree_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                education.append({
                    "degree": match.group(1),
                    "stream": "",  # Would need more parsing
                    "year": "",
                })
        
        return education
    
    def _analyze_gaps(self, analysis: ProfileAnalysis, target_role: str) -> List[str]:
        """Analyze skill gaps for target role."""
        # Common skills for different roles
        role_skills = {
            "software developer": ["programming", "data structures", "algorithms", "git", "testing"],
            "web developer": ["html", "css", "javascript", "react", "node.js", "databases"],
            "data analyst": ["sql", "python", "excel", "data visualization", "statistics"],
            "machine learning engineer": ["python", "machine learning", "deep learning", "tensorflow", "sql"],
            "devops engineer": ["docker", "kubernetes", "ci/cd", "aws", "linux", "scripting"],
            "mobile developer": ["flutter", "react native", "swift", "kotlin", "mobile development"],
            "backend developer": ["python", "java", "sql", "rest api", "microservices", "docker"],
            "frontend developer": ["html", "css", "javascript", "react", "vue", "typescript"],
        }
        
        target_lower = target_role.lower()
        required_skills = []
        
        for role, skills in role_skills.items():
            if role in target_lower or any(word in target_lower for word in role.split()):
                required_skills = skills
                break
        
        if not required_skills:
            # Default skills for any developer role
            required_skills = ["programming", "git", "sql", "testing", "communication"]
        
        # Find gaps
        current_skills = set(s.lower() for s in analysis.skills)
        gaps = [skill for skill in required_skills if skill not in current_skills]
        
        return gaps
    
    def _generate_recommendations(self, analysis: ProfileAnalysis, target_role: str) -> List[str]:
        """Generate career recommendations."""
        recommendations = []
        
        # Based on experience level
        if analysis.experience_level == "fresher":
            recommendations.append("Focus on building projects to showcase your skills")
            recommendations.append("Contribute to open source to gain experience")
            recommendations.append("Apply for internships to gain practical experience")
        
        # Based on skill gaps
        if analysis.skill_gaps:
            gaps_str = ", ".join(analysis.skill_gaps[:3])
            recommendations.append(f"Consider learning: {gaps_str}")
        
        # Based on resume quality
        if len(analysis.skills) < 5:
            recommendations.append("Add more technical skills to your resume")
        
        if not analysis.companies:
            recommendations.append("Include any work experience, even if informal")
        
        if not analysis.education:
            recommendations.append("Add your educational background")
        
        # General recommendations
        recommendations.append("Tailor your resume for each job application")
        recommendations.append("Quantify your achievements with numbers")
        
        return recommendations
    
    def generate_search_keywords(self, analysis: ProfileAnalysis, location: str = None) -> List[str]:
        """Generate search keywords based on profile."""
        keywords = []
        
        # Add skills as keywords
        for skill in analysis.skills[:5]:
            keywords.append(skill)
        
        # Add role-based keywords
        if analysis.experience_level == "fresher":
            keywords.extend(["fresher", "entry level", "junior", "intern"])
        
        # Add location
        if location:
            keywords.append(location)
        
        return keywords


# Global analyzer instance
_analyzer: Optional[ProfileAnalyzer] = None


def get_profile_analyzer() -> ProfileAnalyzer:
    """Get the global profile analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = ProfileAnalyzer()
    return _analyzer
