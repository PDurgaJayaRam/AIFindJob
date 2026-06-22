# MiMo Progress — AIFindJob Session Summary

**Date:** 2026-06-22
**Branch:** harshith-dev
**Commits:** 7 (a30205d, fcd4f6a, e0e2fba, ac2c98a, 41c8ebf, d30a183, 178859c)

---

## What We Built & Fixed

### 1. Multi-Agent Resume Builder (4-Agent Pipeline)

Built a 4-agent system inspired by Claude Resume methodology:

| Agent | Role | What It Does |
|-------|------|--------------|
| **Diagnoser** | ATS Analysis | Reads resume like an ATS system, finds parsing issues, scores 0-100 |
| **Recruiter** | Keyword Optimization | Finds missing keywords from job descriptions, ranks by importance |
| **Rewriter** | XYZ Formula | Rebuilds every bullet: "Accomplished [X], as measured by [Y], by doing [Z]" |
| **Hiring Manager** | Final Scoring | Scores resume 0-50, gives grade (A+ to F), hire/no-hire recommendation |

**Files created:**
- `resume_tailor/agents/__init__.py`
- `resume_tailor/agents/diagnoser.py`
- `resume_tailor/agents/recruiter.py`
- `resume_tailor/agents/rewriter.py`
- `resume_tailor/agents/hiring_manager.py`
- `resume_tailor/agents/orchestrator.py`

**Files modified:**
- `resume_tailor/tailor.py` — Integrated orchestrator, improved prompt, fixed PDF/DOCX
- `resume_tailor/router.py` — Better profile loading, returns full pipeline results
- `resume_tailor/resume_parser.py` — Fixed section detection for headers with colons

### 2. Resume Parser Fixes

**Problem:** Parser wasn't detecting sections with colons (e.g., "EDUCATION:" vs "EDUCATION")

**Fixed:**
- Education parser — now detects "EDUCATION:" and lines containing "education"
- Skills parser — now detects "SKILLS:" and parses "Category: item1, item2" format
- Projects parser — now detects "PROJECTS:" and "ACADEMIC PROJECTS:"
- Certifications parser — now detects "CERTIFICATIONS:"

**Database re-parsed:** Updated both resumes with proper data (5 education, 4 skills, 2 projects, 5 certifications)

### 3. Continuous Live Scraper

**Problem:** Scraping stopped when navigating away from /admin page

**Fixed:**
- Backend now owns the scraping state (`_live_scraper_running` flag)
- Scraper loops continuously with 60-second cycles
- Scrapes 5 portals: Naukri, Indeed, LinkedIn, Shine, Foundit
- Visits each job's detail page for full description
- Saves to database via ingestion engine's `_persist()` with dedup
- Frontend checks backend status on mount

**Files modified:**
- `api/main.py` — Continuous scraper with database persistence and dedup

### 4. Portal URL Fixes

**Problem:** Shine and TimesJobs showed 404 errors

**Fixed:**
- Shine: Fixed from `/job-search/q/...` to `/job-search/...`
- TimesJobs: Removed (site is completely down)
- LinkedIn: Increased timeout to 60s, added better selectors

### 5. Admin Page 404 Fix

**Problem:** Refreshing /admin page gave 404 error

**Fixed:**
- Changed Vite proxy from catch-all `/admin` to specific API paths
- Added missing proxy rules: `/chat`, `/company-research`, `/find-people`, `/scheduler`, `/social`

**File modified:** `frontend-3d/vite.config.js`

### 6. People Finder Fix

**Problem:** All jobs showed same fake contacts (HR@, Hiring Manager@, John Smith@) with 30% confidence

**Fixed:**
- Removed fake/inferred contacts with default names
- Only shows real emails found on company websites
- Better scraping of team/about/contact/careers pages
- Skips generic emails (info@, support@, noreply@)

**File modified:** `people_finder/finder.py`

### 7. JobCard UI Fix

**Problem:** Contacts hidden behind "+12 more..." and skills limited to 5

**Fixed:**
- Shows ALL contacts (removed `.slice(0, 8)` and "+12 more...")
- Shows ALL missing skills (removed `.slice(0, 5)`)
- Increased scroll area from `max-h-48` to `max-h-96`

**File modified:** `frontend-3d/src/components/JobCard.jsx`

### 8. Social Intelligence Module

Built a new module for social job monitoring:

| Source | Method | Auth Required |
|--------|--------|---------------|
| Twitter | Google search + Jina Reader | ❌ No |
| Reddit | RSS feeds | ❌ No |
| LinkedIn | Jina Reader | ❌ No |
| GitHub | Public API | ❌ No |

**Files created:**
- `social_intel/__init__.py` — Core functions
- `social_intel/router.py` — API endpoints
- `ingestion/sources/social_intel.py` — Ingestion source

**New API endpoints:**
```
GET  /social/status
POST /social/search-jobs
POST /social/search-twitter
POST /social/search-reddit
POST /social/search-linkedin
POST /social/research-company
POST /social/monitor-market
```

### 9. Job Data Enrichment

**Problem:** Jobs had missing company names, descriptions, experience, salary

**Fixed:**
- Created `enrich_jobs.py` to visit detail pages and fill missing data
- Continuous scraper now extracts experience and salary from detail pages
- Updated 43 jobs with missing data
- Added `_is_fresher_friendly()` filter to exclude jobs requiring >1 year experience

**Files created:**
- `enrich_jobs.py` — Script to enrich existing jobs with missing data
- `export_jobs.py` — Export jobs to CSV and HTML (Google Sheets style)

**Files modified:**
- `api/main.py` — Added experience/salary extraction and fresher filtering

### 10. Scraper Uses User's Selected Roles

**Problem:** Scraper only searched for "java" jobs, ignoring user's selected roles

**Fixed:**
- Scraper now fetches `desired_roles` from user preferences
- Uses ALL selected roles for searching (Junior Software Developer, Python Developer, etc.)
- Added fresher filtering: excludes jobs with "senior", "lead", "10+ years", etc.
- Naukri URL includes `?experience=0` for fresher jobs

**File modified:** `api/main.py`

### 11. Matches Page Sorting

**Problem:** Jobs on /matches page weren't sorted by date

**Fixed:**
- Added `created_at` to job data returned to frontend
- Ranking now sorts by score first, then by date (newest first)
- New scraped jobs appear at top of /matches page

**Files modified:**
- `matching/router.py` — Added created_at to job data
- `matching/scorer.py` — Sort by score then date

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    INGESTION ENGINE (24/7)                    │
│  RemoteOK + Arbeitnow + Browser Pool + Social Intel          │
│  (Uses user's selected roles + fresher filtering)            │
│                          ↓                                   │
│                    SQLite Database                            │
│                    (Enriched with full data)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Matching │    │ Resume   │    │ People   │
   │ Engine   │    │ Builder  │    │ Finder   │
   │ (sorted  │    │ (4-Agent)│    │ (real    │
   │  by date)│    │          │    │ contacts)│
   └──────────┘    └──────────┘    └──────────┘
```

---

## Data Quality

| Field | Before | After |
|-------|--------|-------|
| Company names | 190 missing | Fixed via enrichment |
| Descriptions | 175 < 50 chars | Fixed via enrichment |
| Locations | 209 missing | Fixed via enrichment |
| Experience | 1028 missing | Now extracted during scraping |
| Salary | 867 missing | Now extracted during scraping |

---

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy (async) + SQLite
- **Frontend:** React 18 + Vite + Tailwind + Three.js
- **AI:** NVIDIA NIM (Llama 3.1) + OpenAI fallback
- **Scraping:** Playwright (browser) + httpx (API)
- **Social:** Jina Reader + RSS + GitHub API

---

## Export Files

- **CSV:** `data/exports/jobs_export_YYYYMMDD_HHMMSS.csv`
- **HTML:** `data/exports/jobs_export_YYYYMMDD_HHMMSS.html` (Google Sheets style viewer)

---

## Git History

```
178859c fix: sort matches by date (newest first) then by score
d30a183 fix: scraper now uses user's selected roles + fresher filtering
41c8ebf feat: enrich job data + extract experience/salary during scraping
ac2c98a docs: add session progress summary
e0e2fba fix: people finder now only shows real contacts
fcd4f6a feat: social intel integration + show all contacts/skills
a30205d feat: multi-agent resume builder, continuous scraper, portal fixes
```

---

## How to Use

1. **Start backend:** `python run_dev.py`
2. **Register/Login:** Select your desired roles and experience level
3. **Upload resume:** System parses your skills and experience
4. **View matches:** Jobs sorted by relevance + date (newest first)
5. **Generate resume:** 4-agent pipeline creates ATS-optimized resume
6. **Find contacts:** Real emails from company websites
7. **Export jobs:** Run `python export_jobs.py` for CSV/HTML view
