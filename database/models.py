"""SQLAlchemy ORM models for the combo AI agent."""
import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from database.engine import Base
import enum


class JobStatus(str, enum.Enum):
    NEW = "new"
    MATCHED = "matched"
    APPLIED = "applied"
    PENDING = "pending"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"


class LeadPriority(str, enum.Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False)
    job_matches = relationship("JobMatch", back_populates="user", cascade="all, delete-orphan")
    custom_resumes = relationship("CustomResume", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(500))
    text_content = Column(Text)
    skills = Column(JSON, default=list)
    experience_years = Column(Float)
    parsed_data = Column(JSON, default=dict)
    
    # Structured resume sections for optimization
    parsed_sections = Column(JSON, default=dict)
    format_preserved = Column(JSON, default=dict)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="resumes")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    desired_roles = Column(JSON, default=list)
    desired_locations = Column(JSON, default=list)
    remote_ok = Column(Boolean, default=True)
    min_salary = Column(Integer)
    skills = Column(JSON, default=list)
    auto_apply_enabled = Column(Boolean, default=False)
    auto_apply_threshold = Column(Float, default=75.0)

    user = relationship("User", back_populates="preferences")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(500), nullable=False)
    company = Column(String(500))
    location = Column(String(500))
    salary = Column(String(500))
    experience_required = Column(String(500))
    skills_required = Column(JSON, default=list)
    description = Column(Text)
    apply_url = Column(Text)
    source = Column(String(100))
    source_url = Column(Text)
    external_id = Column(String(200), nullable=True)
    remote = Column(Boolean, default=False)
    walk_in = Column(Boolean, default=False)
    internship = Column(Boolean, default=False)
    fresher_friendly = Column(Boolean, default=False)
    ats_score = Column(Float)
    match_score = Column(Float)
    status = Column(String(50), default=JobStatus.NEW)
    ai_analysis = Column(JSON, default=dict)
    posted_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    applied_at = Column(DateTime)

    user = relationship("User", back_populates="jobs")
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")
    matches = relationship("JobMatch", back_populates="job", cascade="all, delete-orphan")
    custom_resumes = relationship("CustomResume", back_populates="job", cascade="all, delete-orphan")
    recruiters = relationship("Recruiter", back_populates="job", cascade="all, delete-orphan")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(50), default=JobStatus.APPLIED)
    cover_letter = Column(Text)
    notes = Column(Text)
    screenshots = Column(JSON, default=list)
    applied_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")


class Recruiter(Base):
    __tablename__ = "recruiters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500))
    role = Column(String(500))
    company = Column(String(500))
    linkedin_url = Column(Text)
    email = Column(String(500))
    github = Column(String(500))
    phone = Column(String(500))
    photo_url = Column(Text)
    location = Column(String(500))
    relevance = Column(String(20))
    skills = Column(JSON, default=list)
    contact_type = Column(String(50))
    is_recruiter = Column(Boolean, default=False)
    is_hiring_manager = Column(Boolean, default=False)
    verified = Column(Boolean, default=False)
    outreach_linkedin = Column(Text)
    outreach_email_subject = Column(Text)
    outreach_email_body = Column(Text)
    source = Column(String(100))
    confidence = Column(Float, default=0.5)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("Job", back_populates="recruiters")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False)
    website = Column(Text)
    size = Column(String(100))
    industry = Column(String(500))
    tech_stack = Column(JSON, default=list)
    culture = Column(Text)
    hiring_trend = Column(String(100))
    ai_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(500), nullable=False)
    website = Column(Text)
    email = Column(JSON, default=list)
    phone = Column(JSON, default=list)
    address = Column(String(500))
    niche = Column(String(500))
    pain_signals = Column(JSON, default=list)
    pain_score = Column(Integer, default=0)
    pain_reasoning = Column(Text)
    automation_ideas = Column(JSON, default=list)
    tech_stack = Column(JSON, default=list)
    company_size = Column(String(100))
    intent_score = Column(Float, default=0.0)
    priority = Column(String(50), default=LeadPriority.COLD)
    contact_person = Column(String(500))
    job_title = Column(String(500))
    source = Column(String(100))
    source_url = Column(Text)
    raw_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class NetworkingMessage(Base):
    __tablename__ = "networking_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"), nullable=True)
    message_type = Column(String(100))
    content = Column(Text)
    status = Column(String(50), default="draft")
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AnalyticsLog(Base):
    __tablename__ = "analytics_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class JobMatch(Base):
    """Enhanced job matching with AI analysis"""
    __tablename__ = "job_matches"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Scores
    overall_score = Column(Float)
    skill_score = Column(Float)
    experience_score = Column(Float)
    education_score = Column(Float)
    
    # Analysis
    matched_skills = Column(JSON, default=list)
    missing_skills = Column(JSON, default=list)
    why_good_fit = Column(Text)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="matches")
    user = relationship("User", back_populates="job_matches")


class CustomResume(Base):
    """Custom generated resumes per job with optimization analysis"""
    __tablename__ = "custom_resumes"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Original resume reference
    original_resume_text = Column(Text)
    original_resume_sections = Column(JSON, default=dict)
    
    # Optimized resume content
    resume_text = Column(Text)
    resume_pdf_path = Column(String(500))
    resume_docx_path = Column(String(500))
    
    # Optimization analysis
    match_score = Column(Float, default=0.0)
    matching_skills = Column(JSON, default=list)
    missing_skills = Column(JSON, default=list)
    recommended_skills = Column(JSON, default=list)
    optimization_suggestions = Column(JSON, default=list)
    job_analysis = Column(JSON, default=dict)
    
    # Metadata
    ats_optimized = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    job = relationship("Job", back_populates="custom_resumes")
    user = relationship("User", back_populates="custom_resumes")


class EmailCampaign(Base):
    """Tracks outreach email campaigns."""
    __tablename__ = "email_campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Email details
    to_email = Column(String(500))
    subject = Column(String(500))
    body = Column(Text)
    html_body = Column(Text)
    
    # Tracking
    status = Column(String(50), default="draft")  # draft, sent, opened, replied, bounced
    message_type = Column(String(100))  # cold_email, follow_up, connection_request
    sent_at = Column(DateTime)
    opened_at = Column(DateTime)
    replied_at = Column(DateTime)
    
    # Follow-up tracking
    follow_up_count = Column(Integer, default=0)
    last_follow_up_at = Column(DateTime)
    
    # Metadata
    message_id = Column(String(500))
    error_message = Column(Text)
    campaign_data = Column(JSON, default=dict)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    job = relationship("Job")
    recruiter = relationship("Recruiter")
    user = relationship("User")


class ApplicationSubmission(Base):
    """Tracks automated application submissions."""
    __tablename__ = "application_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Submission details
    apply_url = Column(Text)
    portal = Column(String(100))
    status = Column(String(50), default="pending")  # pending, in_progress, submitted, failed, needs_review
    
    # Form analysis
    total_fields = Column(Integer, default=0)
    fields_filled = Column(Integer, default=0)
    questions_answered = Column(Integer, default=0)
    fields_needing_review = Column(JSON, default=list)
    
    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    time_elapsed_ms = Column(Integer)
    
    # Results
    confirmation_number = Column(String(500))
    error_message = Column(Text)
    screenshot_path = Column(String(500))
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    job = relationship("Job")
    user = relationship("User")


class ScrapedState(Base):
    """Tracks which portal+query+page combinations have been scraped."""
    __tablename__ = "scraped_state"
    
    id = Column(Integer, primary_key=True, index=True)
    portal = Column(String(100), nullable=False)
    query = Column(String(500), nullable=False)
    page_num = Column(Integer, default=0)
    scraped_at = Column(DateTime, default=datetime.datetime.utcnow)

