# Project Goal 4.8 — JOBFinder SaaS + Multi-Agent Architecture

> Authored with GitLab Duo (Claude Opus 4.8). This is the single source of truth for the SaaS direction. If other `.md` files conflict with this, this file wins.

*Last updated: 2026-06-05*
*Status: Planning locked. Build in phase order. Do NOT skip ahead.*

---

## Vision

A SaaS platform for unemployed youth (starting with India, tier-3 college grads). A user logs in, uploads a resume, picks a target role (Java, graphic design, etc.), and the platform:

1. Shows them relevant jobs matched to their resume + role.
2. Generates a custom, ATS-friendly resume per job (keyword-optimized).
3. Tells them which skills are essential and where they are lacking.
4. Finds details of people working at the hiring company (office email, LinkedIn, phone, social media, personal email) so the user can reach out directly.
5. (Later) Auto-applies to jobs via browser automation.

An **admin side** shows job scraping running 24/7 across many sources.

---

## The Core Design Problem (and the solution)

**Problem:** Each user wants different jobs, and scraping must run 24/7 for everyone. Scraping per-user on demand does NOT scale and gets banned.

**Solution — two-sided system:**

1. **Shared ingestion engine (admin, 24/7):** Pulls jobs from many sources into ONE central `jobs` pool, tagged by role/skill/location. It does not care about individual users. It just keeps the pool full.
2. **Per-user matching layer (client, on demand):** When a user logs in, run matching ONLY (no browser) against the already-collected pool, filtered by resume + target role. Matching, ATS scoring, and resume tailoring are pure data/AI ops — fast and ban-free.

**Key rule:** 1000 users must NOT trigger 1000 scrapers. One pool feeds everyone.

---

## Multi-Agent System

This IS a multi-agent system. Each agent has ONE responsibility and is independently restartable. If one breaks, the others keep working. An orchestrator coordinates them.

| Agent | Single Responsibility | Input | Output | Ban/Legal Risk |
|-------|----------------------|-------|--------|----------------|
| **Orchestrator** | Coordinates agents, manages workflow, retries, status | User/admin requests | Routed tasks | None |
| **Scraper / Ingestion Agent** | ONLY collects jobs from sources into the central pool, 24/7 | Source configs | Rows in `jobs` pool | HIGH (isolate per source) |
| **Matching Agent** | ONLY matches pool jobs to a user's resume + role, ATS scoring, skill-gap analysis | Resume + role + pool | Ranked jobs, match scores, missing skills | None |
| **Resume Agent** | ONLY generates custom ATS-friendly resume per job | Resume + job description | Tailored PDF/DOCX | None |
| **People-Finder / Contact Agent** | ONLY finds people at the hiring company (office email, LinkedIn, phone, social media, personal email) | Company + role | Contact records | HIGH (public data only) |
| **Outreach Agent** | ONLY DRAFTS personalized messages per contact/job (user reviews + sends) | Contact + job + resume | Draft messages | MEDIUM (no mass auto-send) |
| **Auto-Apply Agent** (last) | ONLY fills + submits application forms via browser | Job + resume | Submitted application | HIGH (isolate per portal) |

**Isolation principle:** Each agent (especially each scraper/portal and each contact source) is a separate, independently-restartable module. Breaking one MUST NOT break another. This fixes the "fix Naukri, break Indeed" loop.

---

## Target Architecture

- **Frontend:** React + Vite + TailwindCSS + React Three Fiber (Three.js) + Framer Motion. Client app (login, job feed, job detail, custom resume download, contacts, auto-apply trigger) + separate Admin dashboard (live scraping status).
- **Backend:** FastAPI. Auth (JWT via python-jose + passlib), REST API, agent orchestration, AI client.
- **Ingestion workers:** APScheduler or Celery (both in requirements.txt) running scrapers on a schedule, writing to the central pool.
- **Database:** Start SQLite for speed; move to PostgreSQL (asyncpg already in deps) for multi-user + 24/7 writes. SQLite locks under concurrent load.
- **Queue/state:** Redis (in deps) for job queue + scraper status the admin dashboard reads.
- **AI provider:** NVIDIA NIM (Mistral Large 3) primary; multi-provider client already exists in `ai/ai_client.py`.

---

## Build Order (sequential — do NOT skip)

- **Phase 0 — Stabilize (1-2 days):** Rotate the leaked NVIDIA key. Remove legacy/duplicate `.md` files and unused `frontend/src` cruft. Decide SQLite vs Postgres. Make this file the single source of truth.
- **Phase 1 — One reliable ingestion source:** Stop fixing 8 scrapers. Add ONE source with an official API/RSS (Adzuna, RemoteOK, USAJobs, public RSS). Jobs flow into the central pool on a schedule. Zero ban risk. Proves the 24/7 model.
- **Phase 2 — Auth + per-user matching:** JWT signup/login. Resume upload -> parse -> store. Matching endpoint ranks the existing pool against resume + role. Reuse existing `resume_analyzer.py` + `job_saver.py` ATS logic. No browser.
- **Phase 3 — Custom ATS resume per job:** Resume Agent generates tailored, keyword-injected resume per job, exports PDF/DOCX, downloadable. Pure AI, no scraping risk.
- **Phase 4 — Contacts + outreach (drafts only):** People-Finder Agent finds public contact info. Outreach Agent DRAFTS personalized messages; user reviews + sends in batches. NO mass auto-send (domain blacklist + India IT Act / anti-spam risk).
- **Phase 5 — Auto-apply (last, hardest):** Only after everything above is solid. Each portal = isolated optional plugin with a clear failure boundary.
- **Phase 6 — Admin 24/7 dashboard:** Live per-scraper status, last run, jobs collected, errors (from Redis state).

---

## Hard Constraints / Guardrails

- **Never** commit API keys. Keys live only in `.env` (git-ignored). Rotate the leaked NVIDIA key.
- **Public data only** for the People-Finder Agent. No private-data harvesting, no security bypass.
- **No mass auto-send.** AI drafts; human reviews and sends. Protects deliverability and stays legal.
- **One pool feeds all users.** Never scrape per-user on demand.
- **Agent isolation.** One broken agent/source must never break the others.

---

## Why This Fixes the "Fix One, Break Another" Loop

Scrapers today are coupled and central. In this design, each ingestion source is an independent worker writing to a shared pool. If LinkedIn breaks, Adzuna + RemoteOK keep filling the pool, users keep getting jobs, and the admin dashboard shows "LinkedIn: failing." Never blocked by one source again.

---

## People-Finder Agent — Free Public-Source Strategy (No Paid APIs)

No free, legal API returns full contact details. Build from free public sources and accept partial coverage with a confidence score per field. Public data only.

**Free sources:**
- Company website `/team`, `/about`, `/contact` pages (httpx + BeautifulSoup) — most reliable, lowest risk.
- Email pattern inference from company domain + person name (first.last@, flast@, etc.).
- Free email verification via MX/SMTP check (e.g. `verify-email` lib) to drop invalid guesses.
- Search-engine dorks for PUBLIC LinkedIn/social URLs (e.g. `site:linkedin.com/in "HR" "Company"`). Do NOT crawl LinkedIn itself.
- GitHub free API for developer public emails (great for tech companies).
- Contacts extracted from the job posting itself (recruiter name / apply email).

**Avoid:** scraping LinkedIn at scale (ban + legal), buying/using breach data (illegal), bulk-sending to inferred emails (bounces -> domain blacklist).

**Waterfall design:** domain -> team/contact pages -> infer email patterns -> verify via MX/SMTP -> search public social URLs -> store with confidence score (verified vs guessed). Show confidence to the user; user approves who to contact.

**Open-source toolchain (free, wrap each as an isolated, pluggable source — same pattern as CloakBrowser):**

| Tool | Repo | Role in waterfall | License notes |
|------|------|-------------------|---------------|
| **theHarvester** | laramies/theHarvester | Public emails, names, subdomains, hosts for a domain | OSINT tool; pace requests |
| **Photon** | s0md3v/Photon | Crawl company site for emails + social links | Use on team/contact pages |
| **email-verifier** / `verify-email` | AfterShip/email-verifier | Free MX + SMTP mailbox verification | Drop invalid guesses |
| **Sherlock** | sherlock-project/sherlock | Find social accounts by username (400+ sites) | Social field |
| **Maigret** | soxoj/maigret | Advanced profile dossier by username | Stronger social discovery |
| **holehe** | megadose/holehe | Check if an email is registered on 120+ sites | Enrichment |

**Cautions:** these are OSINT/security-research tools. They get rate-limited/blocked if hammered — pace requests and cache results (same discipline as job scrapers). Public data only. Enrich freely, but the USER reviews and sends; never auto-blast (India IT Act / anti-spam).

**Reference:** CloakBrowser (CloakHQ/CloakBrowser) is the model for wrapping OSS as an isolated module. Each People-Finder tool plugs in behind the agent so one breaking/blocked source does not stop the others.

---

## Open Decisions

- [ ] SQLite now vs Postgres now?
- [ ] First ingestion source for Phase 1 (Adzuna / RemoteOK / USAJobs / RSS)?
- [ ] Build 3D React frontend in parallel as morale boost, or after Phase 2?
