"""Phase 3: per-job ATS resume tailoring (see project_goal_4.8.md).

PHASE 4.9 - Resume Preservation Mode:
The Resume Builder AI preserves the user's original resume and does NOT completely
replace the existing content, structure, or formatting.

Key Principles:
1. Keep all existing personal details, education, projects, certifications, internships, 
   achievements, and experience intact unless explicitly requested changes.
2. Preserve the original resume format, section order, and design as much as possible.
3. Never remove important user information simply to increase match percentage.
4. Never generate fake skills, projects, certifications, or work experience.
5. If certain required skills are missing, list them as "Recommended Skills".
6. Generate optimized version that remains true to user's original profile.

Features:
- Resume Match Percentage
- Missing Skills
- Matching Skills  
- Suggested Improvements
- Comparison between Original and Optimized Resume
"""
from resume_tailor.tailor import (
    tailor_resume,
    build_ai_resume,
    build_fallback_resume,
    write_docx,
    write_pdf,
    calculate_match_score,
    get_comparison_data,
)
from resume_tailor.resume_parser import parse_resume_sections, preserve_original_format
from resume_tailor.job_analyzer import (
    analyze_job_description,
    find_missing_skills,
    find_matching_skills,
    get_optimization_suggestions,
)