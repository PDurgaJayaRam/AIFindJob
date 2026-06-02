# OpenClaude Progress — AI Career Agent

**Last Updated:** 2026-06-02
**Latest Commit:** `79ce382` — Fix: Clear SQLAlchemy loggers after DB init to stop log spam

---

## What We Did This Session (2026-06-02)

### 1. Glassdoor Fix Attempt — Disabled Due to IP Block

**Problem:** Glassdoor Cloudflare "Humans only" CAPTCHA blocks all requests from IP `49.43.217.44`.

**Changes made (still in code, Glassdoor disabled by default):**
- `agents/vision_scraper/portal_adapter.py`:
  - Fixed Glassdoor URL format: dynamic `SRCH_IL.0,{loc_len}_KO{kw_start},{kw_end}` instead of hardcoded `SRCH_KO0,4`
  - Updated `build_search_url()` to calculate Glassdoor KO offsets dynamically
- `agents/vision_scraper/hybrid_extractor.py`:
  - Added `GLASSDOOR_EXTRACTION_JS` — dedicated JS extractor using `a[href*="/job-listing/"]` selectors
  - Registered `glassdoor_in` and `glassdoor_us` in `PORTAL_JS_MAP`
- `agents/browser_agent/autonomous_agent.py`:
  - Added Glassdoor login modal dismiss in `_close_popups()` and `_vision_navigate()`
  - Added cookie-clearing between keyword rounds (reset fingerprinting)
  - Added CAPTCHA retry logic (clear cookies + cooldown before retry)
  - Increased pre-Glassdoor delay from 8-15s to 12-20s
  - Added random scroll amounts (500-1200px) for human-like behavior
  - Added +2 extra scrolls for Glassdoor infinite scroll
- `agents/dual_model_orchestrator.py`:
  - Fixed Glassdoor URL format (was `{loc_dash}-{kw_dash}`, now `{kw_dash}-{loc_dash}` with KO offsets)

**Why disabled:** Cloudflare flags the IP at the network level. CloakBrowser stealth (webdriver=false, UA spoofing) only hides browser fingerprint — the CAPTCHA is served before any JS runs. Would need residential proxy to bypass.

**Disabled in:**
- `agents/dual_model_orchestrator.py` — removed from `all_portals` default
- `agents/browser_agent/agent.py` — removed from `_portals` default
- `agents/browser_agent/standalone.py` — removed from default portal string

**Status:** Code is correct and ready if proxy is added later. Currently disabled to avoid wasting 2+ minutes per search on guaranteed CAPTCHA failures.

---

### 2. Browser Crash Recovery

**Problem:** After Cloudflare CAPTCHA, browser context dies (`TargetClosedError`). All subsequent keyword searches fail silently — 15 keywords all returning 0 jobs.

**Fix in `agents/browser_agent/autonomous_agent.py`:**
- Added crash detection in the portal search loop's exception handler
- On `TargetClosedError` or "closed" error: closes old browser, launches new `BrowserController`, continues search
- If recovery fails: sets `browser_dead = True` to stop gracefully

---

### 3. `import random` Bug Fix

**Problem:** Duplicate `import random` inside loop body shadowed the global import, causing `cannot access local variable 'random' where it is not associated with a value` error.

**Fix in `agents/browser_agent/autonomous_agent.py`:**
- Removed 3 duplicate `import random` statements inside functions (lines 601, 830, 879)
- All `random.*` calls now use the top-level `import random` at line 21

---

## Search Test Results (2026-06-02)

After fixes, search for "SQL" in Hyderabad across 7 portals:

| Portal | Jobs Extracted | Status |
|--------|---------------|--------|
| Naukri | 50+50 | Working — 3 pages, DOM pagination |
| Indeed | 13 | Working — detail page visits |
| LinkedIn | 30 | Working — listing page only |
| TimesJobs | 10 | Working — API intercept |
| Shine | 18 | Working — 1 page + detail visits |
| Foundit | 14 | Working — API intercept + detail visits |
| CutShort | 22 | Working — redirected to Naukri |
| **Total** | **207 raw → 29 filtered** | **Saved 19 new, 10 dupes** |

Search completed in ~16 minutes (962s). All 15 keyword rounds attempted. Browser survived entire session.

---

## Files Modified This Session

| File | Changes |
|------|---------|
| `agents/browser_agent/autonomous_agent.py` | Glassdoor modal dismiss, cookie clearing, CAPTCHA retry, random scroll, crash recovery, removed duplicate imports |
| `agents/browser_agent/agent.py` | Removed Glassdoor from default portals |
| `agents/browser_agent/standalone.py` | Removed Glassdoor from default portals |
| `agents/dual_model_orchestrator.py` | Fixed Glassdoor URL, removed from default portals |
| `agents/vision_scraper/portal_adapter.py` | Fixed Glassdoor URL format + build_search_url |
| `agents/vision_scraper/hybrid_extractor.py` | Added GLASSDOOR_EXTRACTION_JS + PORTAL_JS_MAP entries |

---

## Updated Status (All-Time)

| Item | Status |
|------|--------|
| Glassdoor | Disabled (IP blocked by Cloudflare). Code ready for proxy. |
| TimesJobs | Working — 10 jobs/search |
| Description coverage | 47% — detail page visits working |
| Browser crash recovery | Auto-relaunch on TargetClosedError |
| 7 portals operational | Naukri, Indeed, LinkedIn, TimesJobs, Shine, Foundit, CutShort |
