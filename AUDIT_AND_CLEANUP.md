# JOBFinder Project Audit & Cleanup Guide

## 🎯 Current State: What Actually Works

### ACTIVE CODE (Used by the system)
| File | Purpose | Status |
|------|---------|--------|
| `api/main.py` | FastAPI backend - main entry point | ✅ ACTIVE |
| `agents/orchestrator/orchestrator.py` | Main pipeline orchestrator | ✅ ACTIVE |
| `agents/job_discovery/discovery.py` | Job scraping from portals | ✅ ACTIVE |
| `agents/job_intelligence/intelligence.py` | AI job analysis | ✅ ACTIVE |
| `agents/resume_match/matcher.py` | Resume-job matching | ✅ ACTIVE |
| `agents/company_intelligence/intel.py` | Company research | ✅ ACTIVE |
| `agents/people_finder/finder.py` | Find employees | ✅ ACTIVE |
| `agents/networking/messages.py` | Generate outreach messages | ✅ ACTIVE |
| `agents/auto_apply/browser_agent.py` | Auto-apply to jobs | ✅ ACTIVE |
| `agents/tracking/tracker.py` | Application tracking | ✅ ACTIVE |
| `agents/job_saver.py` | Save jobs to database | ✅ ACTIVE |
| `database/models.py` | Database schema | ✅ ACTIVE |
| `database/engine.py` | Database connection | ✅ ACTIVE |
| `ai/ai_client.py` | AI provider client | ✅ ACTIVE |
| `config/settings.py` | App configuration | ✅ ACTIVE |

### DUPLICATE/UNUSED CODE (Can be removed)
| File | Why It's Useless |
|------|------------------|
| `agents/company_intel.py` | DUPLICATE of `company_intelligence/intel.py` |
| `agents/people_finder.py` | DUPLICATE of `people_finder/finder.py` |
| `agents/job_cache.py` | NOT USED by any active code |
| `agents/portal_registry.py` | NOT USED by orchestrator (hardcoded in orchestrator.py) |
| `agents/smart_rate_limiter.py` | NOT USED by active code |
| `agents/profile_analyzer.py` | NOT USED by active code |
| `agents/job_tracker.py` | DUPLICATE of `tracking/tracker.py` |
| `agents/dual_model_orchestrator.py` | OLD - replaced by `orchestrator/orchestrator.py` |
| `agents/resume_analyzer.py` | DUPLICATE of `resume_match/matcher.py` |
| `agents/chat_agent/` | NOT USED by main pipeline |
| `agents/vision_scraper/` | OLD - replaced by `browser_agent/` |
| `agents/ui_tars_agent/` | OLD - not used |
| `scrapers/` | OLD - replaced by `agents/job_discovery/` |
| `workers/` | NOT USED - we use APScheduler now |
| `outreach/` | DUPLICATE - `networking/messages.py` does this |
| `analytics/` | Empty module, not used |
| `enrichment/` | Empty module, not used |
| `saas/` | Empty module, not used |

### API KEYS (What's actually needed)
| Key | Provider | Free Tier | Status |
|-----|----------|-----------|--------|
| `NVIDIA_API_KEY` | NVIDIA NIM | 1000 req/day FREE | ✅ USE THIS |
| `MISTRAL_API_KEY` | Mistral | 1 req/sec FREE | ✅ USE THIS |
| `GEMINI_API_KEY` | Google Gemini | 15 RPM FREE | ✅ USE THIS |
| `OPENAI_API_KEY` | OpenAI | $5 credit | ⚠️ OPTIONAL (costs money) |
| `DEEPSEEK_API_KEY` | DeepSeek | Very cheap | ⚠️ OPTIONAL |
| `ANTHROPIC_API_KEY` | Claude | $5 credit | ⚠️ OPTIONAL (costs money) |

### RECOMMENDATION: Use FREE APIs Only
- **Primary**: NVIDIA NIM (1000 req/day free)
- **Fallback 1**: Mistral (1 req/sec free)
- **Fallback 2**: Google Gemini (15 RPM free)
- **Remove**: OpenAI, DeepSeek, Anthropic keys (they cost money)

## 🚀 How to Run Locally

### Step 1: Install Dependencies
```bash
cd E:/JOBFinder
pip install -r requirements.txt
pip install apscheduler beautifulsoup4 httpx
```

### Step 2: Set Up Database
```bash
# Database is SQLite - auto-creates on first run
# Just make sure data/ folder exists
mkdir -p data
```

### Step 3: Run the Server
```bash
cd E:/JOBFinder
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Open Browser
```
http://localhost:8000
```

### Step 5: Test the Pipeline
```bash
# Register a user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test123"}'

# Login
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test123"}'

# Trigger full pipeline (use token from login)
curl -X POST http://localhost:8000/scheduler/trigger \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🧹 Cleanup Steps (Run These)

### Step 1: Remove Duplicate Files
```bash
cd E:/JOBFinder

# Remove duplicates (already have working versions)
rm agents/company_intel.py  # Use company_intelligence/intel.py
rm agents/people_finder.py  # Use people_finder/finder.py
rm agents/job_tracker.py    # Use tracking/tracker.py
rm agents/resume_analyzer.py  # Use resume_match/matcher.py

# Remove unused modules
rm agents/job_cache.py
rm agents/portal_registry.py
rm agents/smart_rate_limiter.py
rm agents/profile_analyzer.py
rm -rf agents/chat_agent
rm -rf agents/vision_scraper
rm -rf agents/ui_tars_agent
rm -rf scrapers
rm -rf workers
rm -rf outreach
rm -rf analytics
rm -rf enrichment
rm -rf saas
```

### Step 2: Remove Old Files
```bash
rm agents/dual_model_orchestrator.py  # Old orchestrator
rm test_enhanced_features.py
rm test_nvidia_ai.py
rm test_ui_tars.py
rm create_new_tables.py
rm install_dependencies.py
rm proactor_loop.py
rm run_server.py
```

### Step 3: Clean .env File
Keep only:
```
DATABASE_URL=sqlite+aiosqlite:///./data/career_agent.db
NVIDIA_API_KEY=nvapi-xxx
MISTRAL_API_KEY=xxx
GEMINI_API_KEY=xxx
PRIMARY_AI_PROVIDER=nvidia
APP_NAME=JobFinder
APP_ENV=development
SECRET_KEY=your-secret-key
DEBUG=true
PLAYWRIGHT_HEADLESS=false
```

Remove:
- OPENAI_API_KEY (costs money)
- DEEPSEEK_API_KEY (costs money)
- ANTHROPIC_API_KEY (costs money)
- REDIS_URL (not needed with APScheduler)
- BROWSER_PROXY (optional, remove if not using)
- SMTP_* (can add later for email outreach)
