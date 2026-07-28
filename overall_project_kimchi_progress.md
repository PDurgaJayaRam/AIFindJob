# AIFindJob — Overall Project Progress & Deep Dive Summary

**Last updated:** 2026-06-22
**Deep dive by:** Kimchi AI Agent
**Project path:** `AIFindJob/`

> This document captures the complete findings from the Kimchi deep-dive exploration of the AIFindJob codebase. It exists so future sessions can resume context without re-exploring the entire codebase.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Data Flow](#4-data-flow)
5. [Architecture Patterns](#5-architecture-patterns)
6. [Frontend Details](#6-frontend-details)
7. [Admin Dashboard](#7-admin-dashboard)
8. [Infrastructure & Deployment](#8-infrastructure--deployment)
9. [Built vs Planned](#9-built-vs-planned)
10. [Critical Observations & Security Issues](#10-critical-observations--security-issues)

---

## 1. What This Project Is

**AIFindJob** is a SaaS platform aimed at helping unemployed youth in India find jobs, generate ATS-optimized resumes, and reach out to hiring managers. It uses a **two-sided architecture**: a shared job ingestion pool that fills 24/7 (admin-controlled), and a per-user matching layer that instantly scores jobs against uploaded resumes — all without the user ever triggering a scrape.

---

## 2. Tech Stack

### Backend
| Layer | Technology | Version / Details |
|-------|-----------|-------------------|
| Framework | **FastAPI** | Async, mounted sub-routers |
| Database | **SQLAlchemy** (async) | `aiosqlite` driver; PostgreSQL schema exists but SQLite is default |
| ORM | SQLAlchemy 2.0 | Declarative models, `expire_on_commit=False` |
| Migrations | **Alembic** | Listed in requirements but **tables are auto-created on startup** |
| Cache / Broker | **Redis** + **Celery** | Celery Beat for periodic scraping |
| Auth | **JWT** (HS256) | 24h expiry, bcrypt-hashed passwords, in-memory token blacklist |
| Browser Automation | **Playwright** | Chromium (via `playwright install --with-deps chromium`) |
| Scheduling | **APScheduler** | `continuous_scrape_job` (30 min interval) |
| PDF/DOCX | `python-docx`, `reportlab` | Resume exports |
| Email | `smtplib` | TLS, multipart, attachments, batch sending |
| Scraping | `httpx`, `fake-useragent`, Firecrawl CLI, Playwright subprocess |

### AI / LLM Stack
| Provider | Status | Default Model |
|----------|--------|---------------|
| **NVIDIA** (primary) | Active | `meta/llama-3.1-8b-instruct` |
| Mistral | Fallback | `mistralai/mistral-large` |
| OpenAI | Fallback | GPT-4 / GPT-4o-mini |
| DeepSeek | Fallback | Chat models |
| Anthropic | Fallback | Claude variants |
| Local | Fallback | `sentence-transformers` (referenced but **not actively used** in matching) |

### Frontend
| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | **React** | 18.3.1 |
| Build Tool | **Vite** | 5.4.10 |
| Styling | **Tailwind CSS** | 3.4.14 |
| Animations | **Framer Motion** | 11.x |
| 3D Graphics | **Three.js** + `@react-three/fiber` + `@react-three/drei` | 0.169 |
| Routing | **React Router DOM** | 6.27.0 |
| Auth (client) | `localStorage` JWT | `jobfinder_token` key |
| Base Image | `node:20-alpine` | Dev container only |

---

## 3. Project Structure

```
AIFindJob/
├── api/                        # FastAPI main app + lifespan + middleware
│   └── main.py                 # Mounts 9 sub-routers; JWT setup; rate limiting; lifespan
├── database/
│   ├── engine.py               # Async SQLite engine (aiosqlite)
│   └── models.py               # 15 SQLAlchemy models (Users, Jobs, Resumes, etc.)
├── config/
│   ├── settings.py             # Pydantic BaseSettings, lru_cached
│   └── skills.py               # 100+ hardcoded skill keywords for parsing/ATS
├── ingestion/                  # Job ingestion engine (shared pool)
│   ├── engine.py               # Orchestrates sources, deduplication, SSE broadcast
│   ├── base.py                 # BaseSource abstract class
│   └── sources/                # RemoteOK, Arbeitnow, Adzuna, BrowserSource
├── scrapers/                   # HTTP scraper + Firecrawl wrapper
│   ├── ethical_scraper.py      # httpx + fake_useragent rotation
│   ├── firecrawl_scraper.py    # DuckDuckGo fallback search
│   ├── playwight_scraper.py    # Standalone Playwright for Naukri/Indeed/LinkedIn
│   └── utils.py                # Request helpers
├── workers/                    # Celery + Redis periodic tasks
│   └── celery_app.py           # Continuous every 30 min, Browser every 2 hr
├── matching/                   # Per-user job scoring (AI-free hot path)
│   ├── scorer.py               # Regex-based 0-100 scoring
│   └── router.py               # Sliding window fetch, background scrape trigger
├── resume_tailor/              # Custom resume generation per job
│   ├── resume_parser.py        # Regex-based section extraction
│   ├── job_analyzer.py         # Hardcoded 80+ tech term list
│   ├── resume_generator.py     # AI + deterministic fallback
│   └── router.py               # DOCX + PDF export endpoints
├── people_finder/              # Contact discovery + outreach drafts
│   ├── finder.py               # Waterfall: site scraping → email inference → MX verify
│   └── outreach.py             # AI draft generator (drafts only — no send)
├── outreach/                   # Email sending + tracking + follow-ups
│   ├── email_sender.py         # smtplib wrapper, 2s delay between sends
│   ├── email_tracker.py        # JSON persistence in data/email_tracking/
│   └── follow_up_manager.py    # 3-stage schedule (3, 7, 14 days)
├── admin/                      # Backend admin router only
│   └── router.py               # 7 admin endpoints + SSE events
├── agents/                     # Multi-agent system
│   ├── orchestrator.py         # 8 sub-agents + result aggregation
│   ├── chat_agent/             # Tool-router with 7 intents (search, matches, resume, etc.)
│   ├── browser_agent/          # Playwright-based AI-guided navigation
│   ├── auto_apply/             # Browser automation for job portals
│   ├── dual_model_orchestrator.py  # "Brain + Hands" vision pattern
│   ├── resume_analyzer.py      # AI-first + regex fallback parser
│   └── tracking/               # In-memory tracking (no DB persistence)
├── ai/                         # Shared AI client + prompts
│   ├── ai_client.py            # Multi-provider async singleton
│   └── prompts.py              # 8 static prompt templates
├── frontend-3d/                # React SPA (NOT TypeScript)
│   ├── src/
│   │   ├── main.jsx            # 7 routes, no App.jsx wrapper
│   │   ├── pages/              # Landing, Jobs, Matches, Profile, Admin, Login
│   │   ├── components/         # JobCard, OnboardingDialog, StarField
│   │   ├── contexts/           # UserProfileContext (localStorage JWT)
│   │   └── lib/                # api.js (7 admin + 4 live-scraper functions)
│   └── Dockerfile.dev          # Dev only; no production Dockerfile
├── Dockerfile                  # Python 3.12 + Playwright Chromium
├── docker-compose.yml          # 4 services: backend, frontend, redis, postgres
├── .env.example                # 24 environment variables
├── IMPLEMENTATION_PLAN.md      # 7-phase roadmap
├── IMPLEMENTATION_CHECKLIST.md # Phase 1 setup checklist
└── WHATS_NEW.md                # Phase 1 release notes
```

---

## 4. Data Flow

### Step 1 — Job Ingestion (Admin/Backend, 24/7)

```
[RemoteOK API] ──┐
[Arbeitnow API] ─┼→ ingestion/engine.py → deduplication → database (Jobs.user_id=NULL)
[BrowserSource] ─┘                                      ↓
                                       SSE broadcast → Admin Dashboard
```

- **Sources**: RemoteOK (always on), Arbeitnow (opt-in via env), BrowserPool (default ON for 6 portals)
- **Deduplication** (4 tiers):
  1. `external_id` → 2. `source_url` → 3. `apply_url` → 4. Composite of `title + company + source`
- **Trigger**: APScheduler (`continuous_scrape_job` every 30 min) + Celery Beat (browser every 2 hr)
- **SSE**: Live events broadcast to admin dashboard
- **Auto-contact**: After persisting a job, auto-triggers contact finding

### Step 2 — User Registration & Auth

```
POST /auth/register ──→ bcrypt(password) → Users table
POST /auth/login    ──→ JWT (HS256, 24h) → localStorage: jobfinder_token
GET  /auth/me       ──→ decode JWT → user profile
```

- JWT secret from `.env` (`JWT_SECRET_KEY`; default is hardcoded `jobfinder-secret-key-change-in-production`)
- Token blacklist stored in-memory (Python dict) with 300s cleanup task
- **Note**: Admin and user login use the **same token key** in `localStorage` — logging in as one overwrites the other

### Step 3 — Resume Upload & Parse

```
POST /me/resume ──→ PDF/DOCX/TXT upload
                    → agents/resume_analyzer.py (AI-first, regex fallback)
                    → Resume table: text_content, skills[], experience_years, parsed_data
                    → Update UserProfileContext (localStorage)
```

- AI model: `mistralai/mistral-large-3-675b-instruct-2512`
- Extracts: Contact info, summary, skills, experience, projects, education, certifications
- Fallback regex handles 8 section types when AI is unavailable

### Step 4 — Job Matching (Per-User, Instant)

```
GET /me/jobs ──→ sliding window query (default 300, max 1000)
                → scorer.py: 0-100 score
                  base=40 + skill_overlap(up to 40) + role_keywords(up to 20) + fresher_bonus(up to 10)
                → word-boundary regex matching: \b{skill}\b
                → background: if matches < limit//2, trigger _ensure_jobs_for_roles(...)
                → return JSON with matches + scores
```

- **Hot path is AI-free** (regex scoring = sub-second)
- `user_id=NULL` jobs = shared pool
- `user_id!=NULL` jobs = user-specific jobs from scraping
- Background task: if pool has too few matches, triggers parallel scraping for that user's desired roles

### Step 5 — Resume Tailoring (Per-Job)

```
POST /me/jobs/{id}/resume ──→ job_analyzer.py (hardcoded 80+ terms + capitalized acronyms)
                              → resume_generator.py:
                                AI path: temperature=0.3, max_tokens=1500
                                OR deterministic fallback: skill reordering, section injection
                              → ATS optimization: missing skills marked "(Learning)" / "(Familiar)"
                              → DOCX export (python-docx) OR PDF (reportlab)
                              → Save to data/generated_resumes/
                              → Return {filename, download_url, match_score}
```

### Step 6 — Contact Finding

```
POST /me/jobs/{id}/contact ──→ people_finder/finder.py
                              Waterfall:
                              1. Scrape company site pages (/about, /team, /careers, etc.) → conf 0.8
                              2. Email pattern inference (6 patterns: first@, first.last@, etc.) → conf 0.3-0.5
                              3. MX verification via dnspython → adjusts confidence
                              Default names: HR, Hiring Manager, Recruiter, Talent Acquisition, John Smith
                              → Return contacts[] with name, email, confidence, source, verified
```

### Step 7 — Outreach Drafting (Drafts Only — No Send)

```
POST /me/jobs/{id}/outreach ──→ AI draft (temperature=0.5, max_tokens=400)
                                LinkedIn ~280 chars, Email ~1200 chars
                                OR template fallback
                                → No send endpoint — guardrail enforced
```

### Step 8 — Email Sending (If User Chooses to Send)

```
EmailSender (smtplib, TLS, multipart)
  → batch_send() with 2s delay between emails
EmailTracker (JSON in data/email_tracking/)
  → statuses: draft, sent, delivered, opened, replied, bounced
FollowUpManager
  → 3 stages: 3 days (gentle_reminder), 7 days (value_add), 14 days (final_followup)
```

### Step 9 — Chat Agent

```
POST /chat/send ──→ ChatAgent.tool_router()
                    Intent classification (2-tier: exact match → fuzzy → LLM)
                    Intents: job_search, resume_generate, contact_find, outreach, match_score,
                             admin_control, chat
                    → Route to matching/scoring or respond directly
                    Context-aware: user preferences, resume, chat history
```

---

## 5. Architecture Patterns

### Pattern 1: Two-Sided Isolation
- **Shared ingestion pool** (`user_id=NULL`) fills 24/7 independently
- **Per-user matching** runs without scraping — just queries the pool
- If one scraper breaks (e.g., LinkedIn), others keep filling the pool

### Pattern 2: Hot Path vs AI Path
- **Matching**: AI-free regex scoring for instant results
- **Resume**: AI path for quality, deterministic fallback for speed/reliability
- **Contact finding**: Waterfall from high-confidence (site scraping) to low-confidence (inference)

### Pattern 3: Lazy Imports
- Heavy/optional dependencies (Playwright, `dnspython`, etc.) are imported lazily to prevent startup blocking

### Pattern 4: Multi-Provider AI with Fallback
- `ai/ai_client.py` is a singleton with lazy provider initialization
- Tries NVIDIA → OpenAI → DeepSeek → Anthropic → Mistral
- `json_mode` supported for structured outputs

### Pattern 5: Agent Isolation
- Each agent module is independently restartable
- No shared message bus — agents communicate via FastAPI endpoints and database state

### Pattern 6: SSRF/Leak Paranoia in Scrapers
- Browser agent explicitly validates URLs before navigation (scheme whitelist: `http`, `https`)
- Playwright pages closed in `finally` blocks to prevent browser leaks

---

## 6. Frontend Details

### Pages (7 routes in `main.jsx`)
| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `LandingPage` | 3D starfield hero + value props |
| `/login` | `Login` | JWT login (overwrites admin token) |
| `/jobs` | `Jobs` | Search + browse shared pool |
| `/matches` | `Matches` | Per-user scored matches |
| `/profile` | `Profile` | Resume upload, preferences, settings |
| `/admin` | `Admin` | Live scraper control, source health, portal triggers |
| `/contact` | `Contact` | Contact page |

### Key Components
- **`JobCard`**: Match score bar, "Generate Resume" button, "Find Contacts" button
- **`OnboardingDialog`**: 4-step modal (welcome → upload resume → preferences → success)
- **`StarField`**: Decorative 3D particle scene (4000 points, additive blending, `three` + R3F)

### Design System
- **Colors**: `ink` `#05060a`, `nebula` `#7c3aed`, `aqua` `#22d3ee`
- **Style**: Glassmorphism dark theme, custom Tailwind utilities (`glass`, `glow-text`, `grain-overlay`)
- **No TypeScript** — all `.jsx` files
- **No Redux** — React Context + `localStorage` for state

### Dev Proxy (`vite.config.js`)
- Forwards 7 prefixes to `localhost:8000`: `/ingestion`, `/auth`, `/health`, `/me`, `/admin`, `/resume`, `/live-scraper`
- **`/chat` is missing** from the proxy list

---

## 7. Admin Dashboard

- **Backend**: `admin/router.py` (7 endpoints) + `api/main.py` (4 live-scraper endpoints)
- **Frontend**: Single `Admin.jsx` page inside the shared `frontend-3d` SPA (no separate build)
- **Features**:
  - Live browser scraping start/stop with real-time screenshots
  - Pool stats (total jobs, by-source breakdown)
  - Source health cards (OK/FAILING badges)
  - Portal controls for 6 Indian portals (Naukri, Indeed, LinkedIn, Shine, FoundIt, TimesJobs)
  - SSE streaming of live scrape events
  - Contact database stats
- **Polling**: Admin overview every 15s, live scraper status every 2s when active
- **Auth Gap**: No auth/role guards on admin routes; backend endpoints don't enforce `is_admin`

---

## 8. Infrastructure & Deployment

| Aspect | Configuration |
|--------|---------------|
| **Backend container** | Python 3.12 slim + Playwright Chromium |
| **Frontend container** | Node 20 alpine, dev only (`npm run dev`) |
| **Default database** | SQLite (`sqlite+aiosqlite:///./data/jobs.db`) |
| **Optional database** | PostgreSQL 15 (defined in compose but not used by default) |
| **Cache/Broker** | Redis 7 alpine |
| **Web server** | Uvicorn directly (no Nginx) |
| **SSL/TLS** | Not configured |
| **Static files** | FastAPI serves `frontend-3d/dist/` in production |
| **Secrets** | `.env` file only (no Docker secrets/vault) |
| **Scaling** | Single instance |

### Key Infrastructure Gaps
1. **SQLite in production** — `docker-compose.yml` explicitly sets SQLite, even though PostgreSQL service is defined
2. **No production frontend build** — No Dockerfile for `npm run build`; developer must build manually
3. **No reverse proxy** — Uvicorn exposed directly on port 8000
4. **`/chat` proxy gap** — Vite dev proxy missing the chat endpoint
5. **No Celery worker service** — Redis defined but no `celery-worker` or `celery-beat` container
6. **Playwright bloat** — Backend image includes Chromium even for deployments without live scraping

---

## 9. Built vs Planned

| Item | Plan Status | Code Status | Gap |
|------|------------|-------------|-----|
| Shared ingestion pool | ✅ Planned | ✅ Built | None |
| JWT auth | ✅ Planned | ✅ Built | None |
| Regex matching | ✅ Planned | ✅ Built | None |
| **Semantic/embedding matching** | ✅ Planned | ❌ **Not built** | Plan claims "sentence-transformers" but scorer uses regex only |
| ATS resume generator | ✅ Planned | ✅ Built | None |
| People finder | ✅ Planned | ✅ Built | None |
| Outreach drafts | ✅ Planned | ✅ Built | None |
| Email sending | ✅ Planned | ✅ Built | None |
| **Auto-apply agent** | ✅ Planned | ⚠️ **Partial** | Browser automation exists but admin-only `POST /apply` with LOW trust; no safe user-facing endpoint |
| Admin dashboard | ✅ Planned | ✅ Built | None |
| Chat agent | ✅ Planned | ✅ Built | None |
| **TypeScript frontend** | ✅ Planned | ❌ **Not built** | All `.jsx`, no types |
| **3D effects** (tilt, radar, network) | ✅ Planned | ❌ **Not built** | Only `StarField` decorative scene exists |
| **Security Phase 0** | 🔴 Critical | ❌ **Incomplete** | Leaked NVIDIA API key still in `.env`. No admin auth enforcement. No HTTPS. |
| Celery workers in compose | — | ❌ **Not defined** | Redis exists but no worker container |

---

## 10. Critical Observations & Security Issues

1. **🚨 Leaked API Key** — `IMPLEMENTATION_PLAN.md` explicitly warns about a leaked NVIDIA API key in `.env` as the **first and most critical step** (Phase 0.1). This step was **never completed**. The key is still exposed in the codebase.

2. **🚨 Auto-Apply Risk** — The `POST /apply` endpoint in `api/main.py` has a `Trust: LOW` annotation and is **not exposed safely** to regular users. Browser automation for job portals carries high risk of account bans.

3. **🚨 Matching is Not Semantic** — Despite marketing claims in `WHATS_NEW.md` ("AI semantic analysis," "deep semantic analysis"), the actual `matching/scorer.py` uses pure regex-based keyword matching (`\b{skill}\b`). There is no embedding similarity or LLM-based scoring in the hot path.

4. **🚨 SQLite in Production** — Default Docker deployment uses SQLite with `aiosqlite`. This is fine for a single-user demo but risky for multi-user SaaS.

5. **🚨 Admin Routes Unguarded** — The `/admin` frontend route has no auth check, and most backend admin endpoints don't enforce admin privileges.

6. **🚨 Celery/Redis Orphaned** — Redis is defined in `docker-compose.yml` but there is no Celery worker or beat service container. Workers must be started manually.

7. **Token Collision** — Admin login and user login both write to `localStorage['jobfinder_token']`, overwriting each other.

8. **No Production Frontend Dockerfile** — `frontend-3d/` only has `Dockerfile.dev`. Production deploy requires manual `npm run build`.

9. **Schema Drift** — `config/settings.py` defaults to PostgreSQL, but `.env.example` and `docker-compose.yml` both use SQLite.

10. **Proxy Gap** — `vite.config.js` is missing `/chat` from the dev proxy list.

---

## Deep Dive Reports (Ferment Docs)

Individual detailed reports are available in `.kimchi/ferments/019eeeb4-9f1a-76bb-a1e3-51631eec95fc/docs/`:

- `api_layer.md` — FastAPI routes, middleware, JWT, models, background tasks
- `agent_modules.md` — Orchestrator, chat agent, tracking, AI client, prompts, dual model orchestrator, resume analyzer
- `ingestion_scrapers.md` — Ingestion engine, scrapers, Celery workers, deduplication
- `matching_pipeline.md` — Matching, resume tailor, people finder, outreach
- `frontend_structure.md` — React, Vite, Tailwind, Three.js, routes, components
- `admin_dashboard.md` — Admin router, SSE, live scraping, auth gaps
- `infrastructure.md` — Docker, compose, .env, Vite config, Tailwind config
- `build_phases.md` — Implementation plan, checklist, Whats New, gaps analysis

---

*End of summary. For questions about any section, reference the individual deep-dive reports in the ferment docs directory.*
