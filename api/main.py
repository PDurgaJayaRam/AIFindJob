"""FastAPI main application with all routes."""
import os
import sys
import asyncio
import logging
import time

# Structured logging configuration
from logging_config import setup_logging, get_recent_logs
setup_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("api")

# Silence noisy SQLAlchemy engine logs (keep only warnings+)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# Windows fix: Force ProactorEventLoop BEFORE any event loop is created
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import csv
import io
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Depends, Request, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

from database.engine import init_db
import database.models  # Import to register models with Base
from agents.orchestrator.orchestrator import AgentOrchestrator
from agents.tracking.tracker import TrackingAgent
from agents.vision_scraper.models import NavigationStatus


class SearchRequest(BaseModel):
    resume_text: str = ""
    keywords: List[str] = ["Python", "Data Analyst"]
    locations: List[str] = ["Hyderabad"]
    auto_apply: bool = False
    match_threshold: float = 75.0
    max_jobs: int = 20


class LeadRequest(BaseModel):
    companies: List[Dict[str, Any]]
    target_niche: Optional[str] = None


class ComboRequest(BaseModel):
    resume_text: str = ""
    keywords: List[str] = ["Python"]
    locations: List[str] = ["Hyderabad"]
    companies: Optional[List[Dict[str, Any]]] = None
    auto_apply: bool = False
    match_threshold: float = 75.0


orchestrator = AgentOrchestrator()
tracker = TrackingAgent()

# AI Agent for continuous search
from agents.ai_brain.agent import ai_agent
from agents.workflow.multi_agent import workflow

# Store for messages
agent_messages = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Clear SQLAlchemy loggers created during engine init (they add their own handlers)
    for name in ["sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.orm"]:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.WARNING)
        lg.propagate = False
    
    # Start background scheduler for continuous job scraping
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    import os
    
    scheduler = AsyncIOScheduler()
    
    # Configurable interval: set SCRAPE_INTERVAL_MINUTES env var (default: 5)
    scrape_interval = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "5"))
    
    async def continuous_scrape_job():
        """Background job that runs the full pipeline for all active users."""
        import logging
        logger = logging.getLogger("scheduler")
        logger.info("Running scheduled full pipeline...")
        
        try:
            from database.engine import async_session
            from database.models import User, UserPreference, Resume
            from agents.orchestrator.orchestrator import AgentOrchestrator
            from sqlalchemy import select
            
            async with async_session() as session:
                result = await session.execute(select(User).where(User.is_active == True))
                users = result.scalars().all()
                
                for user in users:
                    try:
                        # Get preferences and resume
                        pref_result = await session.execute(
                            select(UserPreference).where(UserPreference.user_id == user.id)
                        )
                        prefs = pref_result.scalar_one_or_none()
                        
                        resume_result = await session.execute(
                            select(Resume).where(Resume.user_id == user.id)
                                .order_by(Resume.created_at.desc()).limit(1)
                        )
                        resume = resume_result.scalar_one_or_none()
                        
                        if not resume:
                            continue
                        
                        keywords = prefs.desired_roles if prefs and prefs.desired_roles else ["Python Developer"]
                        locations = prefs.desired_locations if prefs and prefs.desired_locations else ["Hyderabad"]
                        skills = prefs.skills if prefs and prefs.skills else (resume.skills or [])
                        
                        # Run FULL pipeline: Jobs + Company Intel + People + Outreach
                        orch = AgentOrchestrator()
                        pipeline_result = await orch.run_full_combo(
                            resume_text=resume.text_content or "",
                            keywords=keywords,
                            locations=locations,
                            companies=None,  # Will be discovered during job search
                            auto_apply=prefs.auto_apply_enabled if prefs else False,
                            match_threshold=60.0,
                        )
                        
                        logger.info(f"Pipeline complete for user {user.id}: {pipeline_result}")
                        
                    except Exception as e:
                        logger.error(f"Pipeline error for user {user.id}: {e}")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
    
    scheduler.add_job(
        continuous_scrape_job,
        trigger=IntervalTrigger(minutes=scrape_interval),
        id="continuous_scrape",
        name=f"Continuous job scrape every {scrape_interval} minutes",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Background scheduler started - scraping every {scrape_interval} minutes")
    
    yield
    
    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title="Combo AI Agent",
    description="Autonomous Career Agent + Lead Generation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting for scraping endpoints
from rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing."""
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)")
    return response


# === AUTH CONFIGURATION ===

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def _bcrypt_hash(password: str) -> str:
    """Hash password using bcrypt directly (avoids passlib/bcrypt 5.x incompatibility)."""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _bcrypt_verify(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    import bcrypt
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Extract user from JWT token. Falls back to default user if no token."""
    if credentials is None:
        # Backward-compatible: no token = default user
        from database.engine import async_session
        from database.models import User
        from sqlalchemy import select
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == 1))
            user = result.scalar_one_or_none()
            if not user:
                # Create default user
                # Use bcrypt directly to avoid passlib/bcrypt 5.x incompatibility
                import bcrypt as _bcrypt
                hashed = _bcrypt.hashpw(b"default", _bcrypt.gensalt()).decode()
                user = User(id=1, email="default@local", hashed_password=hashed, full_name="Default User")
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithm=ALGORITHM)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    from database.engine import async_session
    from database.models import User
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user


# Auth models
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Auth endpoints
@app.post("/auth/register")
async def register(req: RegisterRequest):
    """Register a new user."""
    from database.engine import async_session
    from database.models import User
    from sqlalchemy import select

    async with async_session() as session:
        # Check if email exists
        existing = await session.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(
            email=req.email,
            hashed_password=_bcrypt_hash(req.password),
            full_name=req.full_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        token = create_access_token({"sub": str(user.id)})
        logger.info(f"New user registered: {req.email}")
        return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@app.post("/auth/login")
async def login(req: LoginRequest):
    """Login and get JWT token."""
    from database.engine import async_session
    from database.models import User
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == req.email))
        user = result.scalar_one_or_none()
        if not user or not _bcrypt_verify(req.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = create_access_token({"sub": str(user.id)})
        logger.info(f"User logged in: {req.email}")
        return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@app.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    """Get current user info."""
    return {"user_id": user.id, "email": user.email, "full_name": user.full_name}


# Phase 2: per-user matching against the shared pool (see project_goal_4.8.md).
# build_router takes get_current_user to reuse the existing JWT auth dependency.
from matching.router import build_router as _build_me_router
app.include_router(_build_me_router(get_current_user))


@app.get("/")
async def root():
    chat_path = project_root / "frontend" / "public" / "chat.html"
    if chat_path.exists():
        return FileResponse(str(chat_path))
    dashboard_path = project_root / "frontend" / "public" / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(str(dashboard_path))
    return {"status": "ok", "app": "Job AI Agent", "version": "1.0.0"}


@app.get("/dashboard")
async def dashboard():
    dashboard_path = project_root / "frontend" / "public" / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(str(dashboard_path))
    return {"status": "ok", "message": "Dashboard not found"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# === SCHEDULER STATUS ===

@app.get("/scheduler/status")
async def scheduler_status():
    """Check if the background scheduler is running."""
    return {
        "status": "active",
        "scheduler": "APScheduler",
        "interval_minutes": 30,
        "description": "Jobs are scraped automatically every 30 minutes for all active users",
    }


@app.post("/scheduler/trigger")
async def trigger_scrape(user=Depends(get_current_user)):
    """Manually trigger the full pipeline for the current user."""
    from agents.orchestrator.orchestrator import AgentOrchestrator
    from database.engine import async_session
    from database.models import User, UserPreference, Resume
    from sqlalchemy import select
    
    async with async_session() as session:
        # Get preferences and resume
        pref_result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user.id)
        )
        prefs = pref_result.scalar_one_or_none()
        
        resume_result = await session.execute(
            select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
        )
        resume = resume_result.scalar_one_or_none()
        
        if not resume:
            return {"status": "error", "message": "No resume found. Please upload a resume first."}
        
        keywords = prefs.desired_roles if prefs and prefs.desired_roles else ["Python Developer"]
        locations = prefs.desired_locations if prefs and prefs.desired_locations else ["Hyderabad"]
        
        # Run FULL pipeline
        orch = AgentOrchestrator()
        result = await orch.run_full_combo(
            resume_text=resume.text_content or "",
            keywords=keywords,
            locations=locations,
            companies=None,
            auto_apply=prefs.auto_apply_enabled if prefs else False,
            match_threshold=60.0,
        )
        
        return {
            "status": "success",
            "pipeline": result,
            "message": "Full pipeline completed"
        }


# === LIVE SCRAPER MONITOR ===

@app.get("/live-scraper/status")
async def live_scraper_status():
    """Get current live scraping status, screenshot, and activity log."""
    from agents.browser_agent.live_monitor import live_monitor
    return live_monitor.get_status()


@app.post("/live-scraper/start")
async def live_scraper_start():
    """Start a live scraping session with monitoring."""
    from agents.browser_agent.live_monitor import live_monitor
    live_monitor.start_session()
    return {"status": "started", "message": "Live scraper session started"}


@app.post("/live-scraper/stop")
async def live_scraper_stop():
    """Stop the current live scraping session."""
    from agents.browser_agent.live_monitor import live_monitor
    live_monitor.stop_session()
    return {"status": "stopped", "message": "Live scraper session stopped"}


@app.post("/live-scraper/demo")
async def live_scraper_demo(background_tasks: BackgroundTasks):
    """
    Demo mode: open a browser, navigate through several job portals,
    and capture screenshots so you can see the live view working immediately.
    """
    from agents.browser_agent.live_monitor import live_monitor
    live_monitor.start_session()
    background_tasks.add_task(_run_demo_sync)
    return {"status": "demo_started", "message": "Demo is running. Watch the live page for screenshots."}


def _run_demo_sync():
    """Sync wrapper that creates its own event loop with the right policy (Windows)."""
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_run_demo_async())


async def _run_demo_async():
    """Background task that runs the demo."""
    import traceback
    from agents.browser_agent.live_monitor import live_monitor

    try:
        from playwright.async_api import async_playwright
        import os

        live_monitor.update_status(portal="Browser", action="Launching browser...")
        await asyncio.sleep(0.5)

        async with async_playwright() as p:
            headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
            browser = await p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            portals = [
                ("Naukri", "https://www.naukri.com/java-developer-jobs-in-hyderabad"),
                ("Indeed", "https://www.indeed.com/jobs?q=java+developer&l=hyderabad"),
                ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords=java%20developer&location=hyderabad"),
                ("Internshala", "https://internshala.com/internships/java-internship/"),
                ("Wellfound", "https://wellfound.com/jobs"),
            ]

            for name, url in portals:
                if not live_monitor.is_running:
                    break
                try:
                    live_monitor.update_status(portal=name, url=url, action=f"Navigating to {name}...")
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2500)
                    ss_bytes = await page.screenshot(type="jpeg", full_page=False, quality=50)
                    live_monitor.set_screenshot(screenshot_bytes=ss_bytes)
                    live_monitor.update_status(portal=name, url=url, action=f"Captured screenshot of {name}")

                    await page.evaluate("window.scrollBy(0, 500)")
                    await page.wait_for_timeout(1000)
                    ss_bytes = await page.screenshot(type="jpeg", full_page=False, quality=50)
                    live_monitor.set_screenshot(screenshot_bytes=ss_bytes)
                    live_monitor.update_status(portal=name, url=url, action=f"Scrolled {name} jobs list")

                    live_monitor.add_job({
                        "title": f"Sample {name} Job - Java Developer",
                        "company": f"Demo Company {name}",
                        "location": "Hyderabad"
                    })

                    await page.wait_for_timeout(1500)
                except Exception as e:
                    err_short = str(e)[:150] if str(e) else type(e).__name__
                    live_monitor.add_error(f"{name}: {err_short}")
                    live_monitor.update_status(portal=name, action=f"Error on {name}, moving on...")

            live_monitor.update_status(action="Demo complete - visited 5 portals")
            await browser.close()
    except Exception as e:
        err_msg = str(e) or traceback.format_exc() or type(e).__name__
        live_monitor.add_error(f"Demo failed: {err_msg[:2000]}")
        live_monitor.update_status(action=f"Demo error: {err_msg[:100]}")


# === COMPANY RESEARCH ===

@app.get("/company-research/{company_name}")
async def get_company_research(company_name: str, user=Depends(get_current_user)):
    """Get deep research on a specific company."""
    from agents.company_intel import company_researcher
    
    profile = await company_researcher.research_company(company_name)
    return {"status": "success", "company": profile.to_dict()}


@app.post("/company-research/batch")
async def batch_company_research(
    company_names: List[str],
    user=Depends(get_current_user)
):
    """Research multiple companies at once."""
    from agents.company_intel import company_researcher
    
    results = []
    for name in company_names[:10]:  # Limit to 10
        profile = await company_researcher.research_company(name)
        results.append(profile.to_dict())
    
    return {"status": "success", "companies": results}


# === PEOPLE FINDING ===

@app.post("/find-people/{company_name}")
async def find_people(
    company_name: str,
    job_title: str = "",
    user=Depends(get_current_user)
):
    """Find people at a specific company for outreach."""
    from agents.people_finder import people_finder
    
    job_data = {"company": company_name, "title": job_title}
    plan = await people_finder.find_people_for_job(job_data)
    
    return {"status": "success", "outreach_plan": plan.to_dict()}


@app.post("/generate-message")
async def generate_outreach_message(
    company_name: str,
    job_title: str,
    recipient_name: str = "",
    message_type: str = "linkedin",
    user=Depends(get_current_user)
):
    """Generate a personalized outreach message."""
    from agents.networking.messages import NetworkingAgent
    
    networking = NetworkingAgent()
    
    job = {"company": company_name, "title": job_title}
    resume_summary = ""  # Would come from user's resume
    
    if message_type == "referral":
        message = await networking.generate_referral_request(job, resume_summary, recipient_name)
    else:
        message = await networking.generate_job_outreach(job, resume_summary, recipient_name)
    
    return {"status": "success", "message": message}


# === RATE LIMITING ===

class RateLimiter:
    """Simple in-memory sliding window rate limiter."""
    def __init__(self):
        self._requests: Dict[str, List[float]] = {}

    def _clean(self, key: str, window: int):
        now = time.time()
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if now - t < window]

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Return True if request is allowed."""
        self._clean(key, window_seconds)
        if key not in self._requests:
            self._requests[key] = []
        if len(self._requests[key]) >= max_requests:
            return False
        self._requests[key].append(time.time())
        return True


_rate_limiter = RateLimiter()


def rate_limit(max_requests: int, window_seconds: int = 60):
    """Dependency factory for rate limiting endpoints."""
    async def _check(request: Request):
        key = f"{request.url.path}:{request.client.host}"
        if not _rate_limiter.check(key, max_requests, window_seconds):
            raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    return _check


# In-memory log buffer for /api/v1/logs
_log_buffer: List[Dict[str, Any]] = []
_MAX_LOG_ENTRIES = 500


class LogHandler(logging.Handler):
    """Capture log records into an in-memory buffer."""
    def emit(self, record):
        _log_buffer.append({
            "time": self.formatter.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })
        if len(_log_buffer) > _MAX_LOG_ENTRIES:
            _log_buffer.pop(0)


_log_handler = LogHandler()
_log_handler.setFormatter(logging.Formatter("%(asctime)s", "%Y-%m-%d %H:%M:%S"))
logging.getLogger().addHandler(_log_handler)


@app.get("/api/v1/logs")
async def get_logs(level: str = "INFO", limit: int = 100):
    """Get recent log entries."""
    level_upper = level.upper()
    filtered = [e for e in _log_buffer if e["level"] == level_upper or level_upper == "ALL"]
    return {"logs": filtered[-limit:], "total": len(filtered)}


@app.post("/jobs/search", dependencies=[Depends(rate_limit(30, 60))])
async def search_jobs(req: SearchRequest):
    """Run job discovery + intelligence + resume matching pipeline."""
    try:
        result = await orchestrator.run_job_pipeline(
            resume_text=req.resume_text,
            keywords=req.keywords,
            locations=req.locations,
            auto_apply=req.auto_apply,
            match_threshold=req.match_threshold,
            max_jobs=req.max_jobs,
        )
        return {
            "success": True,
            "jobs_discovered": result.jobs_discovered,
            "jobs_matched": result.jobs_matched,
            "applications_submitted": result.applications_submitted,
            "errors": result.errors,
            "jobs": result.jobs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/export/csv")
async def export_jobs_csv(req: SearchRequest):
    """Export job listings as CSV file."""
    try:
        result = await orchestrator.run_job_pipeline(
            resume_text=req.resume_text,
            keywords=req.keywords,
            locations=req.locations,
            auto_apply=False,
            match_threshold=0,
            max_jobs=req.max_jobs,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Title", "Company", "Location", "Source", "Match Score",
            "Skills", "Experience Required", "Salary Range",
            "Remote", "Internship", "Summary", "Job URL"
        ])

        for job in result.jobs:
            writer.writerow([
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("source", ""),
                f"{job.get('match_score', 0):.1f}%",
                ", ".join(job.get("skills", [])),
                job.get("experience_required", ""),
                job.get("salary_range", ""),
                job.get("remote", False),
                job.get("internship", False),
                job.get("summary", "")[:200],
                job.get("source_url", ""),
            ])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=jobs_export.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/leads/enrich")
async def enrich_leads(req: LeadRequest):
    """Run lead enrichment and outreach generation pipeline."""
    try:
        result = await orchestrator.run_lead_pipeline(
            companies=req.companies,
            target_niche=req.target_niche,
        )
        return {
            "success": True,
            "leads_generated": result.leads_generated,
            "messages_generated": result.messages_generated,
            "errors": result.errors,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/combo/run")
async def run_combo(req: ComboRequest):
    """Run both job pipeline and lead pipeline in parallel."""
    try:
        result = await orchestrator.run_full_combo(
            resume_text=req.resume_text,
            keywords=req.keywords,
            locations=req.locations,
            companies=req.companies,
            auto_apply=req.auto_apply,
            match_threshold=req.match_threshold,
        )
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/applications")
async def get_applications(status: Optional[str] = Query(None)):
    apps = await tracker.get_applications(status=status)
    return {"applications": apps}


@app.get("/analytics/outreach")
async def get_outreach():
    outreach = await tracker.get_outreach()
    return {"outreach": outreach}


@app.get("/analytics/dashboard")
async def get_dashboard():
    return await tracker.get_analytics()


@app.post("/resume/parse")
async def parse_resume(file: UploadFile = File(...)):
    """Accept a resume file and extract text from PDF, DOCX, or TXT."""
    try:
        content = await file.read()
        filename = file.filename.lower()
        text = ""

        if filename.endswith(".pdf"):
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(content))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        elif filename.endswith(".docx"):
            from docx import Document
            from io import BytesIO
            doc = Document(BytesIO(content))
            for para in doc.paragraphs:
                text += para.text + "\n"

        elif filename.endswith(".txt"):
            text = content.decode("utf-8", errors="ignore")

        else:
            # Try as plain text fallback
            text = content.decode("utf-8", errors="ignore")

        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from file. Try .txt format.")

        return {"filename": file.filename, "extracted_text": text.strip()[:5000]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {e}")


# === AI AGENT CONTROLS ===

class AgentStartRequest(BaseModel):
    search: str = "Python"
    location: str = "Hyderabad"
    resume_text: str = ""
    auto_apply: bool = False
    match_threshold: float = 75.0


class AgentQuestionRequest(BaseModel):
    question: str


@app.post("/agent/start")
async def start_agent(req: AgentStartRequest):
    """Start the AI agent for continuous job search."""
    try:
        # Set message callback to collect messages
        messages = []
        def msg_callback(msg):
            messages.append({"message": msg, "time": datetime.now().isoformat()})
        
        ai_agent.set_message_callback(msg_callback)
        
        # Start the agent in background
        asyncio.create_task(
            ai_agent.start_continuous_search(
                search=req.search,
                location=req.location,
                resume_text=req.resume_text,
                auto_apply=req.auto_apply,
                match_threshold=req.match_threshold,
            )
        )
        
        return {
            "status": "started",
            "message": f"AI Agent started searching for '{req.search}' in {req.location}",
            "messages": messages,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/stop")
async def stop_agent():
    """Stop the AI agent."""
    ai_agent.stop()
    return {"status": "stopped", "message": "AI Agent stopped"}


@app.get("/agent/status")
async def get_agent_status():
    """Get current agent status."""
    return {
        "is_running": ai_agent.is_running,
        "state": ai_agent.state.value,
        "search": ai_agent.current_search,
        "location": ai_agent.current_location,
        "auto_apply": ai_agent.auto_apply_enabled,
        "total_jobs": len(ai_agent.jobs),
        "jobs_table": ai_agent.get_jobs_table(),
    }


@app.get("/agent/jobs")
async def get_agent_jobs():
    """Get all jobs found by agent in table format."""
    return {
        "jobs": ai_agent.get_jobs_table(),
        "total": len(ai_agent.jobs),
        "export_csv": ai_agent.export_to_csv(),
    }


@app.post("/agent/question")
async def ask_agent(req: AgentQuestionRequest):
    """Ask the AI agent a question."""
    try:
        answer = await ai_agent.answer_question(req.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agent/messages")
async def get_agent_messages():
    """Get all messages from agent."""
    return {"messages": agent_messages}


@app.post("/agent/auto-apply/toggle")
async def toggle_auto_apply(enabled: bool = True):
    """Toggle auto-apply on/off."""
    ai_agent.auto_apply_enabled = enabled
    return {"auto_apply": enabled, "message": f"Auto-apply {'enabled' if enabled else 'disabled'}"}


# === MULTI-AGENT WORKFLOW ENDPOINTS ===

class WorkflowRequest(BaseModel):
    keywords: List[str] = ["Python", "Data Analyst"]
    location: str = "Hyderabad"
    resume_text: str = ""
    auto_apply: bool = False
    match_threshold: float = 75.0
    max_results: int = 20


@app.post("/workflow/run", dependencies=[Depends(get_current_user)])
async def run_workflow(req: WorkflowRequest):
    """Run complete multi-agent workflow: search -> analyze -> apply -> report."""
    try:
        result = await workflow.run_full_workflow(
            keywords=req.keywords,
            location=req.location,
            resume_text=req.resume_text,
            auto_apply=req.auto_apply,
            match_threshold=req.match_threshold,
            max_results=req.max_results,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/search")
async def workflow_search(req: WorkflowRequest):
    """Run search only with multi-agent."""
    try:
        result = await workflow.run_search_only(
            keywords=req.keywords,
            location=req.location,
            max_results=req.max_results,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/dashboard")
async def workflow_dashboard():
    """Get dashboard summary with job counts."""
    return workflow.get_dashboard_summary()


@app.get("/workflow/jobs")
async def workflow_jobs():
    """Get all jobs in table format."""
    return {
        "jobs": workflow.get_jobs_table(),
        "count": len(workflow.jobs)
    }


@app.get("/workflow/progress")
async def workflow_progress():
    """Get current workflow progress."""
    return {
        "progress": workflow.progress,
        "is_running": workflow.is_running,
        "total_jobs": len(workflow.jobs)
    }


@app.post("/workflow/analyze")
async def workflow_analyze(resume_text: str = ""):
    """Analyze existing jobs."""
    try:
        result = await workflow.run_analyze_only(resume_text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === CHAT INTERFACE ===

class ChatRequest(BaseModel):
    user_id: str = ""
    message: str
    resume_text: str = ""
    keywords: str = "Python"
    location: str = "Hyderabad"
    target_count: int = 20
    experience: str = "fresher"
    portals: List[str] = []
    history: List[Dict[str, str]] = []
    jobs: List[Dict[str, Any]] = []


chat_agent_instance = None


@app.post("/chat")
async def chat(req: ChatRequest):
    """Chat with the AI agent."""
    global chat_agent_instance
    if chat_agent_instance is None:
        from agents.chat_agent.agent import ChatAgent
        chat_agent_instance = ChatAgent()

    context = {
        "user_id": req.user_id or "default_user",
        "resume_text": req.resume_text,
        "keywords": req.keywords,
        "location": req.location,
        "target_count": req.target_count,
        "experience": req.experience,
        "portals": req.portals,
        "history": req.history[-10:],
        "jobs": req.jobs,
    }

    try:
        result = await chat_agent_instance.route_message(req.message, context)
        return result
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Chat error: {error_detail}", flush=True)
        return {
            "response": f"Error: {str(e)}",
            "tool_uses": chat_agent_instance.get_tool_log(),
            "jobs": []
        }


# === SAVED JOBS DASHBOARD ===

@app.get("/saved-jobs", dependencies=[Depends(get_current_user)])
async def get_saved_jobs(limit: int = 100, offset: int = 0, status: str = None, days: int = None, sort_by: str = "newest"):
    """Get all saved jobs from database. Sort by 'newest' (default) or 'score'."""
    from agents.job_saver import JobSaver
    saver = JobSaver()
    jobs = await saver.get_all_jobs(limit=limit, offset=offset, status=status, days=days, sort_by=sort_by)
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/saved-jobs/stats", dependencies=[Depends(get_current_user)])
async def get_saved_jobs_stats():
    """Get saved jobs statistics."""
    from agents.job_saver import JobSaver
    saver = JobSaver()
    return await saver.get_stats()


@app.post("/saved-jobs/apply/{job_id}", dependencies=[Depends(get_current_user)])
async def apply_to_saved_job(job_id: int):
    """Mark a job as applied."""
    from database.engine import async_session
    from database.models import Job, JobStatus
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.status = JobStatus.APPLIED
        job.applied_at = datetime.utcnow()
        await session.commit()
        return {"success": True, "job_id": job_id}


# Add datetime import at the top
from datetime import datetime


# === ENHANCED JOB MATCHING ENDPOINTS ===

@app.post("/jobs/{job_id}/analyze", dependencies=[Depends(get_current_user)])
async def analyze_job_match(job_id: int):
    """
    Analyze how well user's resume matches this job
    Uses AI to calculate match scores and identify skill gaps
    """
    from database.engine import async_session
    from database.models import Job, Resume, JobMatch
    from sqlalchemy import select
    from agents.job_matcher.matcher import job_matcher
    import json
    
    async with async_session() as session:
        # Get job
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get user's latest resume (simplified - should use auth)
        result = await session.execute(
            select(Resume).order_by(Resume.created_at.desc()).limit(1)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=404, detail="No resume found. Please upload a resume first.")
        
        # Prepare data
        resume_skills = resume.skills if isinstance(resume.skills, list) else []
        resume_data = {
            'skills': resume_skills,
            'experience_years': resume.experience_years or 0,
            'education': resume.text_content[:500] if resume.text_content else '',
            'name': resume.filename or 'User',
            'email': 'user@example.com',
            'phone': '',
            'location': '',
            'experience': resume.text_content[:1000] if resume.text_content else '',
            'current_role': 'Professional'
        }
        
        job_data = {
            'id': job.id,
            'title': job.title,
            'company': job.company,
            'description': job.description or '',
            'requirements': job.description or ''
        }
        
        # Calculate match
        match_result = job_matcher.calculate_match_score(resume_data, job_data)
        
        # Save to database
        job_match = JobMatch(
            job_id=job_id,
            user_id=resume.user_id,
            overall_score=match_result['overall_score'],
            skill_score=match_result['skill_score'],
            experience_score=match_result['experience_score'],
            education_score=match_result['education_score'],
            matched_skills=match_result['matched_skills'],
            missing_skills=match_result['missing_skills'],
            why_good_fit=match_result['why_good_fit']
        )
        session.add(job_match)
        
        # Update job with match score
        job.match_score = match_result['overall_score']
        
        await session.commit()
        
        return match_result


@app.post("/jobs/{job_id}/generate-resume", dependencies=[Depends(get_current_user)])
async def generate_custom_resume(job_id: int):
    """
    Generate custom resume tailored for this specific job
    Uses AI to optimize content and create ATS-friendly document
    """
    from database.engine import async_session
    from database.models import Job, Resume, JobMatch, CustomResume
    from sqlalchemy import select
    from agents.resume_generator.generator import resume_generator
    
    async with async_session() as session:
        # Get job
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get job match
        result = await session.execute(
            select(JobMatch).where(JobMatch.job_id == job_id).order_by(JobMatch.created_at.desc()).limit(1)
        )
        job_match = result.scalar_one_or_none()
        if not job_match:
            raise HTTPException(
                status_code=404, 
                detail="Please analyze job match first by calling /jobs/{job_id}/analyze"
            )
        
        # Get resume
        result = await session.execute(
            select(Resume).order_by(Resume.created_at.desc()).limit(1)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=404, detail="No resume found")
        
        # Prepare data
        resume_skills = resume.skills if isinstance(resume.skills, list) else []
        resume_data = {
            'name': 'John Doe',  # Should come from user profile
            'email': 'user@example.com',
            'phone': '+1234567890',
            'location': 'City, State',
            'skills': resume_skills,
            'experience_years': resume.experience_years or 0,
            'current_role': 'Professional',
            'experience': resume.text_content[:1000] if resume.text_content else '',
            'education': 'Your Education'
        }
        
        job_data = {
            'id': job.id,
            'title': job.title,
            'company': job.company,
            'description': job.description or '',
            'requirements': job.description or ''
        }
        
        match_data = {
            'matched_skills': job_match.matched_skills if isinstance(job_match.matched_skills, list) else [],
            'missing_skills': job_match.missing_skills if isinstance(job_match.missing_skills, list) else []
        }
        
        # Generate resume
        filename = resume_generator.generate_custom_resume(resume_data, job_data, match_data)
        
        # Save to database
        custom_resume = CustomResume(
            job_id=job_id,
            user_id=resume.user_id,
            resume_docx_path=filename,
            ats_optimized=True
        )
        session.add(custom_resume)
        await session.commit()
        
        return {
            "message": "Resume generated successfully",
            "filename": filename,
            "download_url": f"/download-resume/{custom_resume.id}"
        }


@app.get("/download-resume/{resume_id}")
async def download_custom_resume(resume_id: int):
    """
    Download generated custom resume
    """
    from database.engine import async_session
    from database.models import CustomResume
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(CustomResume).where(CustomResume.id == resume_id)
        )
        custom_resume = result.scalar_one_or_none()
        if not custom_resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        if not os.path.exists(custom_resume.resume_docx_path):
            raise HTTPException(status_code=404, detail="Resume file not found on disk")
        
        return FileResponse(
            custom_resume.resume_docx_path,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=f"resume_{custom_resume.job_id}.docx"
        )


# === VISION-GUIDED SCRAPING ENDPOINTS (V2) ===

class VisionScrapeRequest(BaseModel):
    portal: str
    query: str
    location: str = ""
    max_jobs: int = 100


class VisionBatchRequest(BaseModel):
    query: str
    location: str = ""
    portals: Optional[List[str]] = None
    max_jobs_per_portal: int = 100


vision_orchestrator = None


@app.post("/api/v2/scrape/portal")
async def scrape_portal_vision(req: VisionScrapeRequest):
    """Scrape a single job portal using vision-guided navigation."""
    global vision_orchestrator
    if vision_orchestrator is None:
        from agents.vision_scraper.scraping_orchestrator import ScrapingOrchestrator
        vision_orchestrator = ScrapingOrchestrator()

    try:
        result = await vision_orchestrator.scrape_portal(
            portal_name=req.portal,
            query=req.query,
            location=req.location,
            max_jobs=req.max_jobs,
        )
        return {
            "success": result.status == NavigationStatus.SUCCESS,
            "portal": result.portal_name,
            "status": result.status.value,
            "jobs_count": len(result.jobs),
            "jobs": [job.model_dump() for job in result.jobs],
            "steps_taken": result.steps_taken,
            "time_elapsed_ms": result.time_elapsed_ms,
            "error": result.error_message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v2/scrape/all-portals")
async def scrape_all_portals_vision(req: VisionBatchRequest):
    """Scrape multiple job portals using vision-guided navigation."""
    global vision_orchestrator
    if vision_orchestrator is None:
        from agents.vision_scraper.scraping_orchestrator import ScrapingOrchestrator
        vision_orchestrator = ScrapingOrchestrator()

    try:
        results = await vision_orchestrator.scrape_all_portals(
            query=req.query,
            location=req.location,
            portal_names=req.portals,
            max_jobs_per_portal=req.max_jobs_per_portal,
        )
        summary = {
            portal: {
                "status": r.status.value,
                "jobs_count": len(r.jobs),
                "time_elapsed_ms": r.time_elapsed_ms,
                "error": r.error_message,
            }
            for portal, r in results.items()
        }
        total_jobs = sum(len(r.jobs) for r in results.values())
        return {
            "success": True,
            "total_jobs": total_jobs,
            "portals_scraped": len(results),
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v2/scrape/status")
async def scrape_status():
    """Get rate limit status and orchestrator health."""
    global vision_orchestrator
    if vision_orchestrator is None:
        return {"status": "not_initialized"}

    return {
        "rate_limits": vision_orchestrator.rate_limiter.get_rate_limit_status(),
        "browser_active": not vision_orchestrator.browser.is_browser_crashed(),
    }


@app.on_event("shutdown")
async def shutdown_vision():
    """Clean up vision orchestrator on shutdown."""
    global vision_orchestrator
    if vision_orchestrator:
        await vision_orchestrator.close()


# === PHASE 3: RECRUITER INTELLIGENCE ENDPOINTS ===

class RecruiterRequest(BaseModel):
    job_id: int
    resume_summary: str = ""


class CompanyContactRequest(BaseModel):
    company_name: str
    website: str = ""
    role_hint: str = "recruiter"


class OutreachRequest(BaseModel):
    job_id: int
    recruiter_name: str = ""
    recruiter_email: str = ""
    resume_summary: str = ""
    message_type: str = "email"


recruiter_intelligence = None


@app.post("/api/v3/recruiter/analyze-job")
async def analyze_job_recruiter(req: RecruiterRequest):
    """Full recruiter intelligence analysis for a job."""
    global recruiter_intelligence
    if recruiter_intelligence is None:
        from agents.recruiter_intelligence import RecruiterIntelligence
        recruiter_intelligence = RecruiterIntelligence()

    from database.engine import async_session
    from database.models import Job
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == req.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description or "",
            "source_url": job.source_url or "",
        }

        analysis = await recruiter_intelligence.analyze_job_opportunity(
            job_data=job_data,
            resume_summary=req.resume_summary,
        )

        recruiters_to_save = analysis.get("recruiters", [])
        if recruiters_to_save:
            from database.models import Recruiter
            for r in recruiters_to_save:
                recruiter = Recruiter(
                    name=r.get("name", ""),
                    role=r.get("role", ""),
                    company=job.company,
                    linkedin_url=r.get("linkedin_url", ""),
                    email=r.get("email", ""),
                    source=r.get("source", "ai_search"),
                    confidence=r.get("confidence", 0.5),
                    job_id=job.id,
                )
                session.add(recruiter)
            await session.commit()

        return {
            "success": True,
            "job_id": req.job_id,
            "company_name": analysis.get("company_name", ""),
            "is_actively_hiring": analysis.get("is_actively_hiring", False),
            "hiring_signals": analysis.get("hiring_signals", []),
            "tech_stack": analysis.get("tech_stack", []),
            "company_priority": analysis.get("company_priority", "cold"),
            "recruiters_found": analysis.get("recruiters_found", 0),
            "recruiters": analysis.get("recruiters", []),
            "outreach_draft": analysis.get("outreach_draft", ""),
            "company_intelligence": analysis.get("company_intelligence", {}),
        }


@app.post("/api/v3/recruiter/find-contacts")
async def find_company_contacts(req: CompanyContactRequest):
    """Find contacts for a specific company."""
    global recruiter_intelligence
    if recruiter_intelligence is None:
        from agents.recruiter_intelligence import RecruiterIntelligence
        recruiter_intelligence = RecruiterIntelligence()

    contacts = await recruiter_intelligence.find_contacts_for_company(
        company_name=req.company_name,
        website=req.website,
        role_hint=req.role_hint,
    )

    return {
        "success": True,
        "company": req.company_name,
        "contacts_found": len(contacts),
        "contacts": contacts,
    }


@app.post("/api/v3/recruiter/generate-outreach")
async def generate_outreach(req: OutreachRequest):
    """Generate personalized outreach message."""
    global recruiter_intelligence
    if recruiter_intelligence is None:
        from agents.recruiter_intelligence import RecruiterIntelligence
        recruiter_intelligence = RecruiterIntelligence()

    from database.engine import async_session
    from database.models import Job
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == req.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description or "",
        }

        recruiter = {
            "name": req.recruiter_name or "Hiring Manager",
            "email": req.recruiter_email,
        }

        message = await recruiter_intelligence.generate_outreach(
            job=job_data,
            recruiter=recruiter,
            resume_summary=req.resume_summary,
            message_type=req.message_type,
        )

        return {
            "success": True,
            "message": message,
            "recipient": req.recruiter_name or "Hiring Manager",
            "job": job.title,
        }


@app.get("/api/v3/recruiter/job/{job_id}")
async def get_job_recruiters(job_id: int):
    """Get saved recruiters for a specific job."""
    from database.engine import async_session
    from database.models import Recruiter
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Recruiter).where(Recruiter.job_id == job_id).order_by(Recruiter.confidence.desc())
        )
        recruiters = result.scalars().all()

        return {
            "job_id": job_id,
            "recruiters": [
                {
                    "id": r.id,
                    "name": r.name,
                    "role": r.role,
                    "company": r.company,
                    "linkedin_url": r.linkedin_url,
                    "email": r.email,
                    "source": r.source,
                    "confidence": r.confidence,
                }
                for r in recruiters
            ],
        }


# === PHASE 4: OUTREACH AUTOMATION ENDPOINTS ===

class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    html_body: Optional[str] = None
    job_id: Optional[int] = None
    recruiter_id: Optional[int] = None
    from_name: str = ""
    auto_follow_up: bool = True


class JobOutreachRequest(BaseModel):
    job_id: int
    recruiter_email: str
    recruiter_name: str = ""
    resume_summary: str = ""
    from_name: str = ""


class FollowUpProcessRequest(BaseModel):
    resume_summary: str = ""
    from_name: str = ""


outreach_orchestrator = None


@app.post("/api/v4/outreach/send")
async def send_outreach_email(req: SendEmailRequest):
    """Send a single outreach email."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    result = await outreach_orchestrator.send_outreach_email(
        to_email=req.to_email,
        subject=req.subject,
        body=req.body,
        html_body=req.html_body,
        job_id=req.job_id,
        recruiter_id=req.recruiter_id,
        from_name=req.from_name,
        auto_follow_up=req.auto_follow_up,
    )
    return result


@app.post("/api/v4/outreach/job")
async def send_job_outreach(req: JobOutreachRequest):
    """Generate and send outreach email for a specific job."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    from database.engine import async_session
    from database.models import Job
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == req.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description or "",
        }

        recruiter = {
            "id": req.recruiter_id,
            "name": req.recruiter_name or "Hiring Manager",
            "email": req.recruiter_email,
        }

        result = await outreach_orchestrator.send_job_outreach(
            job=job_data,
            recruiter=recruiter,
            resume_summary=req.resume_summary,
            from_name=req.from_name,
        )
        return result


@app.post("/api/v4/outreach/process-followups")
async def process_follow_ups(req: FollowUpProcessRequest):
    """Process pending follow-up emails."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    results = await outreach_orchestrator.process_follow_ups(
        jobs_data={},
        resume_summary=req.resume_summary,
        from_name=req.from_name,
    )
    return {
        "processed": len(results),
        "results": results,
    }


@app.get("/api/v4/outreach/stats")
async def get_outreach_stats():
    """Get email outreach statistics."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    return outreach_orchestrator.get_email_stats()


@app.get("/api/v4/outreach/history")
async def get_outreach_history(job_id: Optional[int] = None):
    """Get email outreach history."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    return {
        "emails": outreach_orchestrator.get_email_history(job_id=job_id),
    }


@app.get("/api/v4/outreach/email/{email_id}")
async def get_email_record(email_id: str):
    """Get a specific email record."""
    global outreach_orchestrator
    if outreach_orchestrator is None:
        from outreach.orchestrator import OutreachOrchestrator
        outreach_orchestrator = OutreachOrchestrator()

    record = outreach_orchestrator.get_email_record(email_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email record not found")
    return record


# === PHASE 5: AUTO-APPLY AGENT ENDPOINTS ===

class AutoApplyRequest(BaseModel):
    job_id: int
    resume_summary: str = ""
    resume_file_path: Optional[str] = None
    user_review_required: bool = True


class FormAnalyzeRequest(BaseModel):
    apply_url: str
    portal: str = ""


auto_apply_agent = None


@app.post("/api/v5/auto-apply/submit", dependencies=[Depends(rate_limit(10, 60)), Depends(get_current_user)])
async def submit_application(req: AutoApplyRequest):
    """Automatically apply to a job."""
    global auto_apply_agent
    if auto_apply_agent is None:
        from agents.browser_agent.browser_controller import BrowserController
        from agents.auto_apply.auto_apply_agent import AutoApplyAgent
        browser = BrowserController(headless=False)
        auto_apply_agent = AutoApplyAgent(browser=browser)

    from database.engine import async_session
    from database.models import Job, ApplicationSubmission
    from sqlalchemy import select
    import datetime

    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == req.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if not job.apply_url and not job.source_url:
            raise HTTPException(status_code=400, detail="No application URL available")

        apply_url = job.apply_url or job.source_url

        resume_data = {
            "name": "User",
            "email": "",
            "phone": "",
            "location": "",
            "skills": [],
            "experience_years": 0,
            "current_role": "Professional",
            "experience": req.resume_summary,
        }

        job_data = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description or "",
        }

        submission = ApplicationSubmission(
            job_id=req.job_id,
            user_id=1,
            apply_url=apply_url,
            portal=job.source or "unknown",
            status="in_progress",
            started_at=datetime.datetime.utcnow(),
        )
        session.add(submission)
        await session.commit()

        try:
            apply_result = await auto_apply_agent.apply_to_job(
                apply_url=apply_url,
                resume_data=resume_data,
                job_data=job_data,
                resume_file_path=req.resume_file_path,
                user_review_required=req.user_review_required,
            )

            submission.status = "submitted" if apply_result.get("submitted") else "needs_review"
            submission.total_fields = apply_result.get("fields_filled", 0)
            submission.fields_filled = apply_result.get("fields_filled", 0)
            submission.questions_answered = apply_result.get("questions_answered", 0)
            submission.fields_needing_review = apply_result.get("fields_needing_review", [])
            submission.time_elapsed_ms = apply_result.get("time_elapsed_ms", 0)
            submission.completed_at = datetime.datetime.utcnow()

            if apply_result.get("errors"):
                submission.error_message = "; ".join(apply_result["errors"])
                submission.status = "failed"

            await session.commit()

            return {
                "success": apply_result.get("success", False),
                "submission_id": submission.id,
                "status": submission.status,
                "fields_filled": submission.fields_filled,
                "questions_answered": submission.questions_answered,
                "time_elapsed_ms": submission.time_elapsed_ms,
                "errors": apply_result.get("errors", []),
                "fields_needing_review": submission.fields_needing_review,
            }

        except Exception as e:
            submission.status = "failed"
            submission.error_message = str(e)
            submission.completed_at = datetime.datetime.utcnow()
            await session.commit()
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v5/auto-apply/analyze-form")
async def analyze_application_form(req: FormAnalyzeRequest):
    """Analyze an application form without submitting."""
    global auto_apply_agent
    if auto_apply_agent is None:
        from agents.browser_agent.browser_controller import BrowserController
        from agents.auto_apply.auto_apply_agent import AutoApplyAgent
        browser = BrowserController(headless=False)
        auto_apply_agent = AutoApplyAgent(browser=browser)

    try:
        await auto_apply_agent.browser.go_to(req.apply_url, timeout=30000)
        await auto_apply_agent.browser.wait(3)

        form_analysis = await auto_apply_agent.form_analyzer.analyze_form_dom(
            auto_apply_agent.browser.page
        )

        return {
            "success": True,
            "url": form_analysis.url,
            "portal": form_analysis.portal,
            "total_fields": form_analysis.total_fields,
            "can_auto_fill": form_analysis.can_auto_fill,
            "estimated_fill_time_seconds": form_analysis.estimated_fill_time_seconds,
            "fields_needing_review": form_analysis.fields_needing_review,
            "screening_questions": [
                {
                    "question": q.question_text,
                    "type": q.question_type,
                    "needs_review": q.needs_review,
                }
                for q in form_analysis.screening_questions
            ],
            "file_uploads": [
                {"label": f.label, "required": f.required}
                for f in form_analysis.file_uploads
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v5/auto-apply/submissions")
async def get_application_submissions(status: Optional[str] = None):
    """Get application submission history."""
    from database.engine import async_session
    from database.models import ApplicationSubmission
    from sqlalchemy import select

    async with async_session() as session:
        query = select(ApplicationSubmission).order_by(ApplicationSubmission.created_at.desc())
        if status:
            query = query.where(ApplicationSubmission.status == status)
        result = await session.execute(query)
        submissions = result.scalars().all()

        return {
            "submissions": [
                {
                    "id": s.id,
                    "job_id": s.job_id,
                    "portal": s.portal,
                    "status": s.status,
                    "fields_filled": s.fields_filled,
                    "questions_answered": s.questions_answered,
                    "time_elapsed_ms": s.time_elapsed_ms,
                    "error_message": s.error_message,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in submissions
            ],
        }


@app.get("/api/v5/auto-apply/submission/{submission_id}")
async def get_submission_detail(submission_id: int):
    """Get details of a specific application submission."""
    from database.engine import async_session
    from database.models import ApplicationSubmission
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(ApplicationSubmission).where(ApplicationSubmission.id == submission_id)
        )
        submission = result.scalar_one_or_none()
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        return {
            "id": submission.id,
            "job_id": submission.job_id,
            "apply_url": submission.apply_url,
            "portal": submission.portal,
            "status": submission.status,
            "total_fields": submission.total_fields,
            "fields_filled": submission.fields_filled,
            "questions_answered": submission.questions_answered,
            "fields_needing_review": submission.fields_needing_review,
            "started_at": submission.started_at.isoformat() if submission.started_at else None,
            "completed_at": submission.completed_at.isoformat() if submission.completed_at else None,
            "time_elapsed_ms": submission.time_elapsed_ms,
            "error_message": submission.error_message,
            "confirmation_number": submission.confirmation_number,
        }


# ============================================================
# UI-TARS Autonomous Agent (Phase 6)
# ============================================================

class UITarsTaskRequest(BaseModel):
    task: str
    start_url: Optional[str] = "https://www.google.com"
    max_steps: int = 25


ui_tars_browser = None
ui_tars_lock = asyncio.Lock()


async def get_ui_tars_browser():
    """Get or create UI-TARS browser instance."""
    global ui_tars_browser
    if ui_tars_browser is None or ui_tars_browser.is_browser_crashed():
        from agents.browser_agent.browser_controller import BrowserController
        ui_tars_browser = BrowserController(headless=False)
        await ui_tars_browser.start()
    return ui_tars_browser


async def close_ui_tars_browser():
    """Close UI-TARS browser instance."""
    global ui_tars_browser
    if ui_tars_browser:
        try:
            await ui_tars_browser.close()
        except:
            pass
        ui_tars_browser = None


@app.post("/api/v6/ui-tars/run")
async def run_ui_tars_task(request: UITarsTaskRequest):
    """
    Run UI-TARS autonomous agent on any task.
    
    Give it any natural language task like:
    - "Open YouTube and search for 'sao paulo song'"
    - "Book me a flight from NYC to LA"
    - "Fill out this job application form"
    """
    try:
        from agents.vision_scraper.ui_tars_agent import UITarsAgent
        
        mistral_api_key = os.getenv("MISTRAL_API_KEY")
        if not mistral_api_key:
            raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured")
        
        async with ui_tars_lock:
            try:
                browser = await get_ui_tars_browser()
                agent = UITarsAgent(browser, mistral_api_key, max_steps=request.max_steps)
                result = await agent.run(request.task, start_url=request.start_url)
                
                return {
                    "status": result.get("status"),
                    "task": request.task,
                    "steps_taken": result.get("steps", 0),
                    "error": result.get("error"),
                    "action_history": [
                        {
                            "step": h["step"],
                            "action": h["parsed"].get("action_type"),
                            "thought": h["parsed"].get("thought", "")[:200],
                        }
                        for h in result.get("history", [])
                    ],
                }
            finally:
                # Always close browser after task completes
                await close_ui_tars_browser()
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Ensure browser is closed even on error
        await close_ui_tars_browser()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v6/ui-tars/close")
async def close_ui_tars():
    """Force close UI-TARS browser if stuck."""
    await close_ui_tars_browser()
    return {"status": "browser_closed"}


@app.post("/api/v6/ui-tars/run-stream")
async def run_ui_tars_stream(request: UITarsTaskRequest):
    """Run UI-TARS task with real-time streaming updates."""
    from agents.vision_scraper.ui_tars_agent import UITarsAgent
    
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if not mistral_api_key:
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured")
    
    async def event_stream():
        async with ui_tars_lock:
            browser = await get_ui_tars_browser()
            agent = UITarsAgent(browser, mistral_api_key, max_steps=request.max_steps)
            
            # Override run to yield events
            if request.start_url:
                await browser.go_to(request.start_url)
                await browser.wait(2)
            
            viewport = browser.page.viewport_size
            if viewport:
                agent._viewport_width = viewport.get("width", 1400)
                agent._viewport_height = viewport.get("height", 900)
            
            history_text = ""
            last_action = ""
            same_action_count = 0
            
            for step in range(1, request.max_steps + 1):
                if browser.is_browser_crashed():
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Browser crashed'})}\n\n"
                    return
                
                screenshot = await browser.take_screenshot()
                if isinstance(screenshot, str) and screenshot.startswith("screenshot_error"):
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Screenshot failed: {screenshot}'})}\n\n"
                    return
                
                import base64
                if isinstance(screenshot, bytes):
                    screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                else:
                    screenshot_b64 = screenshot
                
                try:
                    response_text = agent._call_mistral(screenshot_b64, request.task, history_text)
                    parsed = agent._parse_action(response_text)
                    
                    yield f"data: {json.dumps({'type': 'step', 'step': step, 'response': response_text[:500], 'action': parsed.get('action_type')})}\n\n"
                    
                    history_text += f"Step {step}: {response_text}\n"
                    agent._history.append({"step": step, "response": response_text, "parsed": parsed})
                    
                    current_action = f"{parsed.get('action_type')}_{json.dumps(parsed.get('action_inputs', {}))}"
                    if current_action == last_action:
                        same_action_count += 1
                        if same_action_count >= 3:
                            yield f"data: {json.dumps({'type': 'complete', 'status': 'loop_detected', 'steps': step})}\n\n"
                            return
                    else:
                        same_action_count = 0
                    last_action = current_action
                    
                    await agent._execute_action(parsed)
                    
                    if parsed.get("action_type") == "finished":
                        yield f"data: {json.dumps({'type': 'complete', 'status': 'success', 'steps': step})}\n\n"
                        return
                    
                    await browser.wait(2)
                    
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    return
            
            yield f"data: {json.dumps({'type': 'complete', 'status': 'timeout', 'steps': request.max_steps})}\n\n"
    
    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_stream(), media_type="text/event-stream")
