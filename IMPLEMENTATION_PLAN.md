# JOBFinder SaaS — Comprehensive Implementation Plan

> Built with ECC harness. Follow phases sequentially. Do NOT skip ahead.
> Last updated: 2026-06-06

---

## Executive Summary

A SaaS platform for unemployed youth in India to find jobs, generate ATS-friendly resumes, and contact hiring managers. The core architecture problem is solved through **two-sided isolation**: shared ingestion pool feeds all users, per-user matching runs instantly without scraping.

---

## The Core Architecture (Solving "Fix One, Break Another")

### Problem
Each portal scraper is coupled - fixing LinkedIn breaks Indeed, fixing one source affects others.

### Solution — Independent Modules
```
ingestion/
├── remoteok.py      # Works now - keep it
├── arbeitnow.py     # Works now - keep it
├── adzuna.py        # Optional - needs API key
└── base.py          # Isolation wrapper
```

Each source writes to **shared pool** independently. If LinkedIn fails, RemoteOK keeps filling the pool. Users never hit the scrapers directly.

---

## Phase 0 — Stabilize & Secure (1-2 days)

### 0.1 Critical Security Fix
- [ ] **Rotate NVIDIA API key immediately** - current key is leaked in `.env`
- [ ] Remove all API keys from codebase - use environment variables only
- [ ] Add `.env` to `.gitignore` (verify it's there)

### 0.2 Documentation Cleanup
Delete conflicting docs, keep only:
- `project_goal_4.8.md` - Single source of truth
- Remove/redundant: `PROJECT_STATUS.md`, `project.md`, `README.md` differences

### 0.3 Dependency Check
- [ ] Verify SQLite works for single-user, Postgres ready for multi-user
- [ ] Check CloakBrowser installation works
- [ ] Verify AI client fallback logic

---

## Phase 1 — Shared Ingestion Engine (1 week)

### Goal
Jobs flow into central pool 24/7. No user triggers scraping.

### 1.1 Verify Current Sources
```python
# ingestion/sources/ - Already working
RemoteOKSource()      # Free public API - no key needed
ArbeitnowSource()     # Free public API - no key needed  
AdzunaSource()        # Needs APP_ID + APP_KEY (optional)
```

### 1.2 Add One Reliable Source
Choose from free/no-key options:
- **RemoteOK** ✅ Already working
- **Arbeitnow** ✅ Already working
- **USAJobs** (government, public API)
- **GitHub Jobs archive** (archived but stable)

### 1.3 Admin Dashboard Endpoints
```
GET  /admin/ingestion/status   # Per-source status
GET  /admin/ingestion/stats    # Jobs collected per source
POST /admin/ingestion/trigger   # Manual trigger
```

### 1.4 Verification
- [ ] Jobs appear in pool without user login
- [ ] Admin can see source status (working/failing)
- [ ] One source failing doesn't block others

---

## Phase 2 — Auth & Per-User Matching (1 week)

### 2.1 JWT Authentication
```python
# Already in api/main.py
POST /auth/register   # Email/password signup
POST /auth/login      # Get JWT token
GET  /auth/me         # Current user info
```

### 2.2 Resume Upload & Parse
```python
POST /me/resume       # Upload PDF/DOCX/TXT
GET  /me/profile      # Parsed skills, roles, experience
```

### 2.3 Matching Pipeline
```python
# matching/scorer.py - Already has fast scorer
GET  /me/jobs         # Match pool against user profile
POST /me/jobs/match   # Force re-match
```

### 2.4 Database Schema (Already exists)
- Users, Resumes, UserPreferences, Jobs, JobMatches, CustomResumes

---

## Phase 3 — Custom ATS Resume Generator (1 week)

### Goal
Generate one ATS-friendly resume per job. No scraping.

### 3.1 Resume Template Engine
```python
# resume_tailor/ - Already partially built
POST /me/jobs/{id}/resume    # Generate tailored resume
GET  /me/jobs/{id}/download  # Download PDF/DOCX
```

### 3.2 ATS Optimization
- Extract keywords from job description
- Inject user skills into job-relevant sections
- Match exact keywords (word-boundary)
- Export clean PDF/DOCX

### 3.3 Skills Gap Analysis
```python
POST /me/jobs/{id}/analyze
Returns: matched_skills, missing_skills, why_good_fit
```

---

## Phase 4 — People Finder (1 week)

### Goal
Find public contacts at hiring companies. Drafts only.

### 4.1 Free Public Sources (No Paid APIs)
```python
# people_finder/finder.py - Already built
1. Company team/about pages (BeautifulSoup)
2. Email pattern inference (first.last@, flast@)
3. GitHub API for developer emails
4. Search engine dorks for public LinkedIn profiles
5. Contact from job posting itself
```

### 4.2 Confidence Scoring
- Verified email (SMTP check) - HIGH confidence
- Inferred pattern - MEDIUM confidence
- Social profile found - LOW confidence (user must verify)

### 4.3 Outreach Drafts
```python
# people_finder/outreach.py - Already built
POST /me/jobs/{id}/outreach
Returns: draft message, reminder "Review yourself before sending"
```

---

## Phase 5 — Auto-Apply Agent (2 weeks)

### Goal
Browser automation for individual portals. Isolated plugins.

### 5.1 Portal Plugin Architecture
```python
# Each portal = isolated module
auto_apply/
├── plugins/
│   ├── naukri.py
│   ├── indeed.py
│   ├── linkedin.py
│   └── glassdoor.py
├── base_plugin.py    # Common interface
└── controller.py   # Orchestrates plugins
```

### 5.2 Isolation Pattern
- Each plugin has separate session/context
- Failing plugin doesn't crash others
- Clear failure boundaries per portal

### 5.3 User Flow
```
1. User selects "Auto-Apply" on matched job
2. Modal shows portal status (✓ Naukri, ✗ LinkedIn down)
3. User confirms before automation runs
4. Result: applied, needs_review, failed
```

---

## Phase 6 — Admin 24/7 Dashboard (1 week)

### Goal
Monitor all ingestion sources in real-time.

### 6.1 Live Monitoring
```python
# admin/router.py - Already exists
GET /admin/dashboard     # Summary stats
GET /admin/sources       # Per-source status
GET /admin/logs          # Recent errors
```

### 6.2 Source Health
- Last run time, jobs collected, error count
- Red/green status for each source
- Manual retry button

---

## Frontend — 3D Experience (Parallel with Phase 2+)

### Tech Stack
- React 18 + Vite + TypeScript
- Three.js via React Three Fiber
- TailwindCSS + Framer Motion
- React Router for SPA navigation

### Pages
```
/
  ├── Landing (3D hero animation)
  ├── Login / Register
  ├── /me
  │   ├── Dashboard (job stats, ATS scores)
  │   ├── Jobs (matched jobs table, filters)
  │   ├── Job/:id (details, resume download, contacts, apply)
  │   └── Settings (preferences, resume upload)
  └── /admin
      ├── Sources (live scraping status)
      ├── Jobs (pool stats)
      └── Logs
```

### 3D Experience Elements
- Hero section: Interactive job search visualization
- Job cards: Hover 3D tilt effect
- Skills radar: 3D chart of skill matches
- Company network: 3D graph of contacts

---

## Security Guardrails

1. **Never** commit API keys - use `.env` only
2. **Public data only** for people finding - no private harvesting
3. **Drafts only** - AI writes outreach, user sends
4. **Portal isolation** - one scraper failing doesn't break others
5. **Rate limiting** - pacing on all external requests

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Jobs in pool (24h) | 500+ |
| Matching latency | < 2 seconds |
| Resume generation | < 5 seconds |
| ATS pass rate | 3x improvement |
| User applications tracked | 100+/day |

---

## Next Action

Start with **Phase 0.1** — rotate the leaked NVIDIA key. This is critical before any other work.