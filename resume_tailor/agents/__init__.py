"""Multi-agent resume builder system.

Four specialized agents work together to create an unstoppable resume:
1. The Diagnoser - Analyzes job requirements and identifies gaps
2. The Recruiter - Understands ATS systems and recruiter preferences
3. The Rewriter - Rewrites content for maximum impact
4. The Hiring Manager - Final review and quality scoring
"""
from resume_tailor.agents.orchestrator import ResumeOrchestrator

__all__ = ["ResumeOrchestrator"]
