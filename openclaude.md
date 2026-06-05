# Project Status - AI Career Agent
**Last Updated:** 2026-06-02  
**Total Commits:** 17  
**Current Jobs in DB:** 783  

---

## Project Overview

An autonomous AI-powered career agent that scrapes jobs from multiple portals, analyzes resume-job matches, generates custom resumes, finds recruiters, sends outreach emails, and auto-fills application forms. Built with Python (FastAPI + Playwright + SQLAlchemy) and a React/Vite frontend.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), SQLite |
| Browser Automation | Playwright (Chromium) + CloakBrowser (stealth) |
| AI/LLM | Mistral API (vision), OpenAI-compatible endpoints |
| Frontend | React 18, Vite, Recharts, Tailwind CSS |
| Scraping | Playwright + DOM extraction, Vision-guided navigation |
| Database | SQLite (`data/career_agent.db`) |

---

## Project Structure

```
Project/
├── api/
│   └── main.py                    # FastAPI app - ALL API endpoints (1561 lines)
├── agents/
│   ├── chat_agent/
│   │   └── agent.py               # Chat interface - routes user messages to tools
│   ├── ai_brain/
│   │   └── agent.py               # AI agent for continuous job search
│   ├── orchestrator/
│   │   └── orchestrator.py        # Main pipeline orchestrator (search → match → apply)
│   ├── job_discovery/             # Job search across portals
│   ├── job_intelligence/          # Job analysis and scoring
│   ├── job_matcher/
│   │   └── matcher.py             # Resume-job matching with AI scoring
│   ├── job_saver.py               # Saves jobs to database
│   ├── resume_analyzer.py         # Resume parsing and skill extraction
│   ├── resume_generator/
│   │   └── generator.py           # Custom resume generation (DOCX)
│   ├── resume_match/              # Resume matching logic
│   ├── recruiter_intelligence/    # Recruiter finding + outreach drafts
│   ├── company_intelligence/      # Company research and analysis
│   ├── networking/                # Networking message generation
│   ├── people_finder/             # Find recruiters/contacts
│   ├── auto_apply/
│   │   └── auto_apply_agent.py    # Automated job application submission
│   ├── browser_agent/
│   │   └── browser_controller.py  # Playwright browser wrapper
│   ├── vision_scraper/
│   │   ├── ui_tars_agent.py       # UI-TARS autonomous vision agent
│   │   ├── vision_agent.py        # Vision-based page analysis
│   │   ├── scraping_orchestrator.py # Multi-portal scraping coordinator
│   │   ├── portal_adapter.py      # Portal-specific adapters
│   │   ├── hybrid_extractor.py    # Hybrid DOM + vision extraction
│   │   ├── rate_limiter.py        # Rate limiting for portals
│   │   ├── config.py              # Scraper configuration
│   │   └── models.py              # Data models
│   ├── workflow/
│   │   └── multi_agent.py         # Multi-agent workflow coordination
│   ├── tracking/
│   │   └── tracker.py             # Application tracking
│   └── skills/                    # Skills analysis tools
├── database/
│   ├── engine.py                  # SQLAlchemy engine setup
│   └── models.py                  # 14 ORM models (329 lines)
├── outreach/
│   ├── orchestrator.py            # Email outreach coordinator
│   ├── email_sender.py            # SMTP email sending
│   ├── email_tracker.py           # Email open/reply tracking
│   └── follow_up_manager.py       # Automated follow-up scheduling
├── frontend/
│   ├── public/
│   │   ├── chat.html              # Chat UI (564 lines) - main interface
│   │   └── dashboard.html         # Job dashboard (299 lines)
│   ├── src/
│   │   ├── App.jsx                # React app root
│   │   ├── main.jsx               # React entry point
│   │   ├── index.css              # Styles
│   │   └── components/
│   │       ├── Dashboard.jsx      # Dashboard view
│   │       ├── JobSearch.jsx      # Job search form
│   │       ├── Analytics.jsx      # Analytics view
│   │       ├── ComboRun.jsx       # Combined pipeline
│   │       ├── LeadGen.jsx        # Lead generation
│   │       └── Layout.jsx         # App layout
│   ├── package.json
│   └── vite.config.js
├── data/
│   └── career_agent.db            # SQLite database
├── .env                           # API keys (MISTRAL_API_KEY, etc.)
├── requirements.txt               # Python dependencies
├── CLAUDE.md                      # Coding guidelines
└── README.md
```

---

## Database Models (14 tables)

| Model | Purpose | Fields |
|-------|---------|--------|
| **User** | User accounts | email, password, name |
| **Resume** | Uploaded resumes | filename, text, skills, experience_years |
| **UserPreference** | Search preferences | roles, locations, salary, auto-apply settings |
| **Job** | Job listings | title, company, location, salary, description, apply_url, source, posted_date, match_score |
| **Application** | Job applications | job_id, status, cover_letter, screenshots |
| **JobMatch** | AI match analysis | overall_score, skill_score, matched/missing skills |
| **CustomResume** | Generated resumes | resume_text, pdf/docx paths, ats_optimized |
| **Recruiter** | Found recruiters | name, role, company, linkedin, email, confidence |
| **Company** | Company profiles | name, size, industry, tech_stack, culture |
| **Lead** | Sales leads | company, contacts, pain_score, intent_score |
| **NetworkingMessage** | Outreach messages | content, status, sent_at |
| **EmailCampaign** | Email campaigns | subject, body, status, follow-up tracking |
| **ApplicationSubmission** | Auto-apply tracking | portal, fields_filled, confirmation_number |
| **AnalyticsLog** | Event tracking | event_type, event_data |

---

## API Endpoints (50+)

### Core Pipeline (v1)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves chat.html |
| `/dashboard` | GET | Serves dashboard.html |
| `/health` | GET | Health check |
| `/jobs/search` | POST | Run full job pipeline |
| `/jobs/export/csv` | POST | Export jobs as CSV |
| `/leads/enrich` | POST | Lead enrichment pipeline |
| `/combo/run` | POST | Run job + lead pipelines |

### Chat Interface
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Chat with AI agent |

### Saved Jobs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/saved-jobs` | GET | Get all saved jobs |
| `/saved-jobs/stats` | GET | Job statistics |
| `/saved-jobs/apply/{id}` | POST | Mark job as applied |

### Job Matching (v2)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/jobs/{id}/analyze` | POST | AI match analysis |
| `/jobs/{id}/generate-resume` | POST | Generate custom resume |
| `/download-resume/{id}` | GET | Download generated resume |

### Vision Scraping (v2)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/scrape/portal` | POST | Scrape single portal |
| `/api/v2/scrape/all-portals` | POST | Scrape all portals |
| `/api/v2/scrape/status` | GET | Rate limit status |

### Recruiter Intelligence (v3)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v3/recruiter/analyze-job` | POST | Full recruiter analysis |
| `/api/v3/recruiter/find-contacts` | POST | Find company contacts |
| `/api/v3/recruiter/generate-outreach` | POST | Generate outreach message |
| `/api/v3/recruiter/job/{id}` | GET | Get job's recruiters |

### Outreach Automation (v4)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v4/outreach/send` | POST | Send outreach email |
| `/api/v4/outreach/job` | POST | Generate + send job outreach |
| `/api/v4/outreach/process-followups` | POST | Process pending follow-ups |
| `/api/v4/outreach/stats` | GET | Email statistics |
| `/api/v4/outreach/history` | GET | Email history |

### Auto-Apply Agent (v5)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v5/auto-apply/submit` | POST | Auto-apply to job |
| `/api/v5/auto-apply/analyze-form` | POST | Analyze application form |
| `/api/v5/auto-apply/submissions` | GET | Submission history |

### UI-TARS Autonomous Agent (v6)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v6/ui-tars/run` | POST | Run autonomous task |
| `/api/v6/ui-tars/close` | POST | Force close browser |
| `/api/v6/ui-tars/run-stream` | POST | Streaming task execution |

### Agent Controls
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agent/start` | POST | Start continuous search |
| `/agent/stop` | POST | Stop agent |
| `/agent/status` | GET | Agent status |
| `/agent/jobs` | GET | Agent's found jobs |
| `/workflow/run` | POST | Multi-agent workflow |
| `/workflow/progress` | GET | Workflow progress |

---

## Job Portals (9 Portals)

| Portal | Status | Jobs Scraped | Notes |
|--------|--------|-------------|-------|
| **Naukri** | Working | 283 | Primary portal, most reliable |
| **LinkedIn** | Working | 201 | Good extraction, anti-bot handled |
| **Indeed** | Working | 148 | Solid results |
| **Shine** | Working | 74 | Consistent |
| **Foundit** | Working | 34 | Fixed URL format (/srp/results) |
| **Cutshort** | Working | 34 | Startup-focused |
| **TimesJobs** | Low | 5 | Underperforming |
| **Glassdoor** | Blocked | 2 | Anti-bot CAPTCHA triggers after ~1 keyword |
| **Web** | Limited | 2 | Generic web scraping |

---

## Features Implemented (17 Features)

### 1. Multi-Portal Job Scraping
- Playwright-based browser automation
- 9 job portals with individual adapters
- Anti-detection delays (3-7s between portals)
- URL encoding for special characters
- Zero-result fast skip (no retries)

### 2. Resume Parsing & Analysis
- PDF, DOCX, TXT file parsing
- Skill extraction
- Experience level detection
- Fresher identification

### 3. AI Job Matching
- Resume-job match scoring (0-100%)
- Skill gap analysis
- Experience score calculation
- Education matching
- "Why good fit" AI explanation

### 4. Custom Resume Generation
- ATS-optimized resume creation
- Tailored to specific job descriptions
- DOCX output format
- Highlights matched skills

### 5. Chat Interface
- Natural language job search
- Intent classification
- Tool routing (search, analyze, apply)
- Full job descriptions in responses
- HTML sanitization for scraped data

### 6. Job Dashboard
- Job listing table with filters
- Statistics by portal
- Export to CSV
- Apply tracking

### 7. Recruiter Intelligence
- AI-powered recruiter finding
- LinkedIn profile discovery
- Company contact research
- Confidence scoring

### 8. Outreach Automation
- Personalized email generation
- SMTP email sending
- Open/reply tracking
- Automated follow-up sequences

### 9. Auto-Apply Agent
- Automated form filling
- Application submission tracking
- Field detection and mapping
- User review mode

### 10. UI-TARS Vision Agent
- Screenshot-based page understanding
- Natural language task execution
- Click, type, scroll actions
- Loop detection
- Streaming progress updates

### 11. Experience Filtering
- Post-scrape fresher filtering
- Regex-based experience extraction
- Non-tech job rejection
- Description-level experience check

### 12. Anti-Detection
- Random delays between requests
- User-agent rotation
- Portal-specific workarounds
- CAPTCHA detection

### 13. Data Sanitization
- HTML tag stripping
- Newline sanitization in titles/companies
- JSON column handling
- URL encoding

### 14. Multi-Agent Workflow
- Search → Analyze → Apply pipeline
- Parallel portal scraping
- Progress tracking
- Error recovery

### 15. Company Intelligence
- Company research
- Tech stack identification
- Hiring trend analysis
- Culture assessment

### 16. Lead Generation
- Company contact finding
- Pain point scoring
- Outreach message generation
- Lead prioritization

### 17. Application Tracking
- Application status tracking
- Interview scheduling
- Rejection handling
- Analytics dashboard

---

## Git History (17 Commits)

| # | Commit | Description |
|---|--------|-------------|
| 17 | `9f80900` | Fix: Glassdoor URL format, foundit uses /srp/results |
| 16 | `0a82407` | Fix: Glassdoor anti-bot, foundit URL, no-results detection |
| 15 | `a7e3bbd` | Fix: foundit uses /srp/results?query=keyword+location, re-enable glassdoor |
| 14 | `9d37c7f` | Fix: foundit and LinkedIn portals actually working |
| 13 | `acc09e8` | Fix: foundit 404, no-results fast skip, portal retry blocking |
| 12 | `032e44f` | Fix: duplicate job error, foundit 404, keyword truncation, stricter fresher filtering |
| 11 | `a31f108` | Fix: LinkedIn extraction bug, stronger fresher filtering, API job descriptions, anti-detection |
| 10 | `c109f5e` | Fix: form experience setting now overrides resume analysis |
| 9 | `bd7b9b7` | Fix: skip Glassdoor detail pages, close leaked tabs, filter DataAnnotation spam |
| 8 | `bedd809` | Fix: search ALL portals, not just first 3; reject Cloudflare error descriptions |
| 7 | `bdc22e1` | Strip HTML tags from job descriptions in chat and dashboard |
| 6 | `775bcbf` | Show full job descriptions in chat and dashboard |
| 5 | `4a57d02` | Visit ALL job detail pages from every portal, remove detail visit cap |
| 4 | `ceffb18` | Fix experience filtering: better regex, stricter non-tech rejection, more detail visits |
| 3 | `6d6f0be` | Replace URL/DOM experience filtering with robust post-scrape filtering |
| 2 | `67a5a26` | Improve job search: experience-aware URLs, network intercept, better extraction |
| 1 | `1ac0660` | First commit |

---

## Known Issues & Limitations

### Critical
- **Glassdoor CAPTCHA**: IP-level Cloudflare block (requires residential proxy). CloakBrowser handles fingerprint detection but can't bypass IP reputation blocking.

### Moderate
- **Description coverage**: Only 47% of jobs have full descriptions (368/783) — improved extraction logic with portal-specific selectors
- **User auth**: No real authentication implemented (uses hardcoded user_id=1)
- **Email sending**: Requires SMTP configuration in .env

### Minor
- **React frontend**: Components exist but main UI is chat.html (vanilla JS)
- **Skills.sh integration**: External API, may have rate limits
- **Vision agent**: Requires Mistral API key for screenshot analysis

---

## Environment Variables Required

```env
MISTRAL_API_KEY=           # For UI-TARS vision agent
SMTP_HOST=                 # Email sending (optional)
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
BROWSER_PROXY=             # Residential proxy for Glassdoor (optional)
                            # Format: http://user:pass@proxy:port
```

---

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn api.main:app --reload --port 8000

# Access
# Chat: http://localhost:8000/
# Dashboard: http://localhost:8000/dashboard
# API Docs: http://localhost:8000/docs
```

---

## Database Stats (as of 2026-05-28)

| Metric | Value |
|--------|-------|
| Total Jobs | 783 |
| With Apply URL | 773 (98.7%) |
| With Description | 368 (47%) |
| By Portal | Naukri: 283, LinkedIn: 201, Indeed: 148, Shine: 74, Foundit: 34, Cutshort: 34, TimesJobs: 5, Glassdoor: 2, Web: 2 |
| Date Range | May 18 - May 26, 2026 |

---

## Next Steps / TODO

### In Progress
1. **Fix Glassdoor**: Add residential proxy support (BROWSER_PROXY env var) — code ready, needs proxy config
2. **Improve description coverage**: Enhanced extraction with portal-specific selectors, increased detail visit limit

### Pending
3. **Add user authentication**: Real user system
4. **Deploy**: Set up production deployment
5. **Improve React frontend**: Migrate from chat.html to React components
6. **Add tests**: Unit and integration tests
7. **Rate limiting**: Better portal-specific rate limits
8. **Monitoring**: Add logging and error tracking

### Completed (Recent)
- ✅ CloakBrowser integration with proxy support
- ✅ Cleaned up redundant anti-detection code (CloakBrowser handles at C++ level)
- ✅ Improved description extraction (more selectors, better fallback)
- ✅ Increased detail page visit limit (15 → 25)
- ✅ Extended skills pattern matching (50+ technologies)
