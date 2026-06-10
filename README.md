# JOBFinder SaaS — AI Career Agent for Unemployed Youth

> **Single source of truth:** See `project_goal_4.8.md` for the complete vision and architecture.
> **Build order:** Follow phases sequentially. Do NOT skip ahead.

---

## The Mission

Help unemployed youth in India (especially tier-3 college graduates) find jobs by:
1. **Auto-scraping** jobs 24/7 into a shared pool
2. **Matching** jobs against user's resume + target role
3. **Generating** custom ATS-friendly resumes per job
4. **Finding** contacts at hiring companies (HR, Developer, Manager, etc.)
5. **Auto-applying** with browser automation (isolated per portal)

---

## Architecture

```
Shared Pool (Admin, 24/7)
       ↓
Per-User Matching (Instant, no scraping)
       ↓
Custom Resume + Contacts (Pure AI)
       ↓
Auto-Apply (Optional, isolated)
```

Each portal/scraper is **independent** - if LinkedIn breaks, other sources keep filling the pool.

---

## Quick Start

### 1. Setup Environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Server
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 4. Access
- Chat: http://localhost:8000/
- Dashboard: http://localhost:8000/dashboard

---

## Build Phases

| Phase | Goal | Status |
|-------|------|--------|
| Phase 0 | Stabilize + rotate keys | ✅ Ready |
| Phase 1 | Shared ingestion (24/7) | 🔄 Working (RemoteOK, Arbeitnow) |
| Phase 2 | Auth + matching | ✅ Built |
| Phase 3 | Custom ATS resumes | 🔄 In progress |
| Phase 4 | People finder | 🔄 Built |
| Phase 5 | Auto-apply | ⏳ Pending |
| Phase 6 | Admin dashboard | 🔄 Built |

---

## Documentation

- `project_goal_4.8.md` - Complete vision and architecture
- `IMPLEMENTATION_PLAN.md` - Detailed implementation phases
- `CLAUDE.md` - Coding guidelines

---

## License

MIT