"""Phase 3 endpoints: generate + download a tailored resume for a pool job.

Mounted under /me, reusing the JWT get_current_user dependency.

PHASE 4.9 - Updated for Resume Preservation:
- Preserves original resume content, structure, and formatting
- Provides comprehensive match analysis
- Shows comparison between original and optimized versions
"""
from __future__ import annotations

import os
import re
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from database.engine import async_session
from database.models import Resume, Job, CustomResume
from resume_tailor.tailor import (
    tailor_resume, write_docx, write_pdf, 
    get_comparison_data, _job_keywords
)
from resume_tailor.job_analyzer import analyze_job_description, find_missing_skills, find_matching_skills, calculate_match_score

logger = logging.getLogger("resume_tailor")
_OUTPUT_DIR = os.path.join("data", "generated_resumes")


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["resume-tailor"])

    async def _load_profile(user_id: int) -> dict | None:
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                return None
            
            parsed = resume.parsed_data or {}
            parsed_sections = resume.parsed_sections or {}
            text = resume.text_content or ""
            
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text) if text else None
            phone_match = re.search(r'[\+]?[\d\s\-\(\)]{7,20}', text) if text else None
            linkedin_match = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', text, re.IGNORECASE) if text else None
            github_match = re.search(r'github\.com/[\w\-]+', text, re.IGNORECASE) if text else None
            
            education_list = parsed_sections.get("education", [])
            education_text = ""
            if education_list:
                edu_parts = []
                for edu in education_list:
                    if isinstance(edu, dict):
                        raw = edu.get("raw", "")
                    else:
                        raw = str(edu)
                    raw = re.sub(r'\s+', ' ', raw).strip()
                    raw = raw.lstrip('•-›·⁃ ').strip()
                    if raw and len(raw) > 5:
                        edu_parts.append(raw)
                education_text = "\n".join(edu_parts[:5])
            if not education_text:
                education_text = parsed.get("education", "")
            
            projects_list = parsed_sections.get("projects", [])
            certifications_list = parsed_sections.get("certifications", [])
            achievements_list = parsed_sections.get("achievements", [])
            experience_list = parsed_sections.get("experience", [])
            
            name = parsed.get("name", "")
            if not name:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                for line in lines[:5]:
                    if '@' not in line and not re.search(r'\d{5,}', line):
                        if len(line) < 50:
                            name = line
                            break
            
            skills_raw = resume.skills or parsed_sections.get("skills", [])
            skills = []
            for s in skills_raw:
                s_clean = re.sub(r'\s+', ' ', s).strip()
                s_clean = s_clean.lstrip('•-›·⁃ ').strip()
                if ':' in s_clean:
                    parts = s_clean.split(':')
                    items = parts[1].strip().split(',')
                    for item in items:
                        item = item.strip()
                        if item and len(item) > 1:
                            skills.append(item)
                elif s_clean and len(s_clean) > 1:
                    skills.append(s_clean)
            
            return {
                "name": name or (resume.filename or "Candidate").rsplit(".", 1)[0],
                "email": parsed.get("email") or (email_match.group(0) if email_match else ""),
                "phone": parsed.get("phone") or (phone_match.group(0) if phone_match else ""),
                "linkedin": parsed.get("linkedin") or (linkedin_match.group(0) if linkedin_match else ""),
                "github": parsed.get("github") or (github_match.group(0) if github_match else ""),
                "skills": skills,
                "experience_text": text,
                "education": education_text,
                "resume_id": resume.id,
                "parsed_sections": parsed_sections,
                "original_text": text,
                "projects": projects_list,
                "certifications": certifications_list,
                "achievements": achievements_list,
                "experience": experience_list,
            }

    @router.post("/jobs/{job_id}/resume")
    async def generate_resume(job_id: int, user=Depends(get_current_user)):
        """Generate an ATS resume tailored to a pool job for the current user.
        
        PRESERVES original resume while optimizing for the target job.
        """
        logger.info("Generating resume for user=%d, job=%d", user.id, job_id)
        profile = await _load_profile(user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="No resume found. POST /me/resume first.")
        
        logger.info("Profile loaded: name=%s, skills=%d, experience=%s, education=%s",
                    profile.get("name", "?"), len(profile.get("skills", [])),
                    "yes" if profile.get("experience") else "no",
                    "yes" if profile.get("education") else "no")

        async with async_session() as session:
            job_row = await session.execute(select(Job).where(Job.id == job_id))
            job = job_row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            job_data = {
                "title": job.title,
                "company": job.company,
                "description": job.description or "",
                "skills_required": job.skills_required or [],
            }

        # Get original text for comparison
        original_text = profile.get("original_text", "") or profile.get("experience_text", "")
        
        # Generate optimized resume with 4-agent pipeline
        resume_text, mode, analysis = await tailor_resume(profile, job_data)
        
        # Validate: ensure we have real content before writing files
        if not resume_text or len(resume_text.strip()) < 50:
            logger.error("Resume generation produced empty/too-short output (%d chars). Mode: %s", len(resume_text or ""), mode)
            raise HTTPException(status_code=500, detail=f"Resume generation failed — got {len(resume_text or '')} chars. Check logs.")
        
        logger.info("Generated resume: %d chars, mode=%s", len(resume_text), mode)
        
        # Calculate match data
        match_score = analysis.get("match_score", 0)
        matching_skills = analysis.get("matching_skills", [])
        missing_skills = analysis.get("missing_skills", [])
        pipeline_metadata = analysis.get("metadata", {})
        diagnosis = analysis.get("diagnosis", {})
        recruiter_findings = analysis.get("recruiter_findings", {})
        hiring_review = analysis.get("hiring_manager_review", {})

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        docx_filename = f"resume_user{user.id}_job{job_id}.docx"
        pdf_filename = f"resume_user{user.id}_job{job_id}.pdf"
        docx_path = os.path.join(_OUTPUT_DIR, docx_filename)
        pdf_path = os.path.join(_OUTPUT_DIR, pdf_filename)
        write_docx(resume_text, docx_path, profile_name=profile.get("name", ""))
        try:
            write_pdf(resume_text, pdf_path, profile_name=profile.get("name", ""))
        except Exception as e:
            logger.info(f"PDF generation fallback: {e}")
            pdf_path = None

        async with async_session() as session:
            cr = CustomResume(
                job_id=job_id,
                user_id=user.id,
                resume_text=resume_text,
                resume_docx_path=docx_path,
                resume_pdf_path=pdf_path,
                ats_optimized=True,
                original_resume_text=original_text,
                original_resume_sections=profile.get("parsed_sections", {}),
                match_score=match_score,
                matching_skills=matching_skills,
                missing_skills=missing_skills,
                job_analysis=analysis.get("job_analysis", {}),
            )
            session.add(cr)
            await session.commit()
            await session.refresh(cr)

        # Return comprehensive response with full pipeline results
        return {
            "custom_resume_id": cr.id,
            "mode": mode,
            "preview": resume_text[:800],
            "download_url": f"/me/resume/{cr.id}/download",
            "pdf_available": pdf_path is not None,
            # Match Analysis
            "match_score": match_score,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            # 4-Agent Pipeline Results
            "pipeline": {
                "diagnosis": {
                    "ats_score": diagnosis.get("ats_score", 0),
                    "parsing_issues": diagnosis.get("parsing_issues", []),
                    "extracted_keywords": diagnosis.get("extracted_keywords", []),
                },
                "recruiter": {
                    "repeated_keywords": recruiter_findings.get("repeated_keywords", [])[:10],
                    "missing_keywords": recruiter_findings.get("missing_keywords", [])[:10],
                    "top_10_to_add": recruiter_findings.get("top_10_to_add", []),
                },
                "hiring_manager": {
                    "scores": hiring_review.get("scores", {}),
                    "grade": hiring_review.get("grade", "N/A"),
                    "hire_recommendation": hiring_review.get("hire_recommendation", "N/A"),
                    "strengths": hiring_review.get("strengths", []),
                    "weaknesses": hiring_review.get("weaknesses", []),
                    "top_3_fixes": hiring_review.get("top_3_fixes_before_submitting", []),
                },
                "metadata": pipeline_metadata,
            },
            "optimization_suggestions": analysis.get("optimization_suggestions", []),
            # Comparison data
            "comparison": {
                "original_preview": original_text[:400] if original_text else "",
                "optimized_preview": resume_text[:400],
                "skills_preserved": len(profile.get("skills", [])),
            }
        }

    @router.get("/resume/{custom_resume_id}")
    async def get_resume_analysis(custom_resume_id: int, user=Depends(get_current_user)):
        """Get detailed analysis of a generated resume including comparison data."""
        async with async_session() as session:
            row = await session.execute(
                select(CustomResume).where(CustomResume.id == custom_resume_id)
            )
            cr = row.scalar_one_or_none()
            if not cr or cr.user_id != user.id:
                raise HTTPException(status_code=404, detail="Resume not found")
            
            # Get job info for context
            job_row = await session.execute(select(Job).where(Job.id == cr.job_id))
            job = job_row.scalar_one_or_none()
            
            return {
                "custom_resume_id": cr.id,
                "job": {
                    "title": job.title if job else "Unknown",
                    "company": job.company if job else "Unknown",
                },
                # Match Analysis
                "match_score": cr.match_score,
                "matching_skills": cr.matching_skills or [],
                "missing_skills": cr.missing_skills or [],
                "optimization_suggestions": cr.optimization_suggestions if hasattr(cr, 'optimization_suggestions') else [],
                # Full comparison
                "comparison": {
                    "original_text": cr.original_resume_text or "",
                    "optimized_text": cr.resume_text or "",
                    "original_sections": cr.original_resume_sections or {},
                    "job_analysis": cr.job_analysis or {},
                }
            }

    @router.get("/resume/{custom_resume_id}/download")
    async def download_resume(custom_resume_id: int, user=Depends(get_current_user)):
        """Download a previously generated tailored resume (owner only)."""
        async with async_session() as session:
            row = await session.execute(
                select(CustomResume).where(CustomResume.id == custom_resume_id)
            )
            cr = row.scalar_one_or_none()
            if not cr or cr.user_id != user.id:
                raise HTTPException(status_code=404, detail="Resume not found")
            
            # Prefer PDF if available, otherwise DOCX
            if cr.resume_pdf_path and os.path.exists(cr.resume_pdf_path):
                return FileResponse(
                    cr.resume_pdf_path,
                    media_type="application/pdf",
                    filename=f"tailored_resume_{cr.job_id}.pdf",
                )
            
            if cr.resume_docx_path and os.path.exists(cr.resume_docx_path):
                return FileResponse(
                    cr.resume_docx_path,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    filename=f"tailored_resume_{cr.job_id}.docx",
                )
            
            raise HTTPException(status_code=404, detail="Resume file missing on disk")

    @router.get("/resume/{custom_resume_id}/compare")
    async def compare_resumes(custom_resume_id: int, user=Depends(get_current_user)):
        """Get side-by-side comparison of original vs optimized resume."""
        async with async_session() as session:
            row = await session.execute(
                select(CustomResume).where(CustomResume.id == custom_resume_id)
            )
            cr = row.scalar_one_or_none()
            if not cr or cr.user_id != user.id:
                raise HTTPException(status_code=404, detail="Resume not found")
            
            original = cr.original_resume_text or ""
            optimized = cr.resume_text or ""
            
            return {
                "custom_resume_id": cr.id,
                "match_percentage": cr.match_score,
                "comparison": {
                    "original": {
                        "content": original,
                        "sections": cr.original_resume_sections or {},
                    },
                    "optimized": {
                        "content": optimized,
                        "sections": {},  # Could be parsed if needed
                    }
                },
                "analysis": {
                    "matching_skills": cr.matching_skills or [],
                    "missing_skills": cr.missing_skills or [],
                    "job_analysis": cr.job_analysis or {},
                },
                "suggested_improvements": cr.optimization_suggestions if hasattr(cr, 'optimization_suggestions') else []
            }

    @router.post("/jobs/{job_id}/analyze")
    async def analyze_resume_match(job_id: int, user=Depends(get_current_user)):
        """Analyze match between user's resume and a specific job WITHOUT generating resume.
        
        Returns:
        - Resume Match Percentage
        - Missing Skills
        - Matching Skills
        - Suggested Improvements
        """
        profile = await _load_profile(user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="No resume found. POST /me/resume first.")

        async with async_session() as session:
            job_row = await session.execute(select(Job).where(Job.id == job_id))
            job = job_row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            job_data = {
                "title": job.title,
                "company": job.company,
                "description": job.description or "",
                "skills_required": job.skills_required or [],
            }

        # Analyze without generating
        job_analysis = analyze_job_description(job_data)
        skills = profile.get("skills", [])
        match_score = calculate_match_score(skills, job_analysis["required_skills"])
        matching_skills = find_matching_skills(skills, job_analysis["required_skills"])
        missing_skills = find_missing_skills(skills, job_analysis["required_skills"])

        return {
            "job_id": job_id,
            "job_title": job.title,
            "job_company": job.company,
            "match_score": match_score,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "job_analysis": job_analysis,
            "suggested_improvements": [
                "Reorder skills to prioritize job-matching skills",
                "Enhance experience bullet points with action verbs",
                f"Consider learning: {', '.join(missing_skills[:5])}" if missing_skills else "All required skills matched!",
            ]
        }

    return router