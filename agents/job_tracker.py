"""Job Tracking Dashboard - Track applications and provide analytics.

Features:
- Application status tracking
- Deadline management
- Follow-up reminders
- Success analytics
- Pipeline visualization
"""
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ApplicationStatus(Enum):
    """Job application statuses."""
    DISCOVERED = "discovered"
    VIEWED = "viewed"
    INTERESTED = "interested"
    APPLIED = "applied"
    APPLICATION_SENT = "application_sent"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_DONE = "interview_done"
    REJECTED = "rejected"
    OFFER_RECEIVED = "offer_received"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    WITHDRAWN = "withdrawn"


@dataclass
class JobApplication:
    """A single job application."""
    job_id: str
    job_title: str
    company: str
    portal: str
    apply_url: str
    
    # Status
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    match_score: float = 0.0
    
    # Timestamps
    discovered_at: datetime = field(default_factory=datetime.now)
    applied_at: Optional[datetime] = None
    last_follow_up: Optional[datetime] = None
    next_follow_up: Optional[datetime] = None
    interview_date: Optional[datetime] = None
    
    # Notes
    notes: str = ""
    rejection_reason: str = ""
    
    # Tracking
    follow_up_count: int = 0
    viewed_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "portal": self.portal,
            "apply_url": self.apply_url,
            "status": self.status.value,
            "match_score": self.match_score,
            "discovered_at": self.discovered_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "last_follow_up": self.last_follow_up.isoformat() if self.last_follow_up else None,
            "next_follow_up": self.next_follow_up.isoformat() if self.next_follow_up else None,
            "interview_date": self.interview_date.isoformat() if self.interview_date else None,
            "notes": self.notes,
            "rejection_reason": self.rejection_reason,
            "follow_up_count": self.follow_up_count,
            "viewed_count": self.viewed_count,
        }


class JobTracker:
    """Track job applications and provide analytics."""
    
    def __init__(self):
        self.applications: Dict[str, JobApplication] = {}
        self._load_from_file()
    
    def _load_from_file(self):
        """Load applications from file."""
        try:
            with open("data/job_tracker.json", "r") as f:
                data = json.load(f)
                for job_id, app_data in data.items():
                    app = JobApplication(
                        job_id=job_id,
                        job_title=app_data.get("job_title", ""),
                        company=app_data.get("company", ""),
                        portal=app_data.get("portal", ""),
                        apply_url=app_data.get("apply_url", ""),
                        status=ApplicationStatus(app_data.get("status", "discovered")),
                        match_score=app_data.get("match_score", 0.0),
                        notes=app_data.get("notes", ""),
                        rejection_reason=app_data.get("rejection_reason", ""),
                        follow_up_count=app_data.get("follow_up_count", 0),
                        viewed_count=app_data.get("viewed_count", 0),
                    )
                    if app_data.get("discovered_at"):
                        app.discovered_at = datetime.fromisoformat(app_data["discovered_at"])
                    if app_data.get("applied_at"):
                        app.applied_at = datetime.fromisoformat(app_data["applied_at"])
                    if app_data.get("last_follow_up"):
                        app.last_follow_up = datetime.fromisoformat(app_data["last_follow_up"])
                    if app_data.get("next_follow_up"):
                        app.next_follow_up = datetime.fromisoformat(app_data["next_follow_up"])
                    if app_data.get("interview_date"):
                        app.interview_date = datetime.fromisoformat(app_data["interview_date"])
                    
                    self.applications[job_id] = app
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Error loading job tracker: {e}")
    
    def _save_to_file(self):
        """Save applications to file."""
        try:
            data = {job_id: app.to_dict() for job_id, app in self.applications.items()}
            with open("data/job_tracker.json", "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving job tracker: {e}")
    
    def add_application(self, job_data: Dict) -> JobApplication:
        """Add a new job application."""
        job_id = job_data.get("job_id") or job_data.get("source_url", "")
        
        if job_id in self.applications:
            # Update existing
            app = self.applications[job_id]
            if job_data.get("match_score", 0) > app.match_score:
                app.match_score = job_data["match_score"]
            return app
        
        app = JobApplication(
            job_id=job_id,
            job_title=job_data.get("title", ""),
            company=job_data.get("company", ""),
            portal=job_data.get("source", ""),
            apply_url=job_data.get("apply_url") or job_data.get("source_url", ""),
            match_score=job_data.get("match_score", 0.0),
        )
        
        self.applications[job_id] = app
        self._save_to_file()
        
        logger.info(f"Added application: {app.job_title} at {app.company}")
        return app
    
    def update_status(self, job_id: str, status: ApplicationStatus, notes: str = ""):
        """Update application status."""
        if job_id not in self.applications:
            logger.warning(f"Application not found: {job_id}")
            return
        
        app = self.applications[job_id]
        app.status = status
        
        if status == ApplicationStatus.APPLIED:
            app.applied_at = datetime.now()
        
        if notes:
            app.notes = notes
        
        self._save_to_file()
        logger.info(f"Updated {app.job_title} status to {status.value}")
    
    def schedule_follow_up(self, job_id: str, days_from_now: int = 7):
        """Schedule a follow-up for an application."""
        if job_id not in self.applications:
            return
        
        app = self.applications[job_id]
        app.next_follow_up = datetime.now() + timedelta(days=days_from_now)
        self._save_to_file()
    
    def record_follow_up(self, job_id: str):
        """Record that a follow-up was sent."""
        if job_id not in self.applications:
            return
        
        app = self.applications[job_id]
        app.last_follow_up = datetime.now()
        app.follow_up_count += 1
        
        # Schedule next follow-up if not rejected
        if app.status not in [ApplicationStatus.REJECTED, ApplicationStatus.OFFER_RECEIVED]:
            app.next_follow_up = datetime.now() + timedelta(days=7)
        
        self._save_to_file()
    
    def get_pipeline(self) -> Dict[str, List[Dict]]:
        """Get applications organized by status (pipeline view)."""
        pipeline = {status.value: [] for status in ApplicationStatus}
        
        for app in self.applications.values():
            pipeline[app.status.value].append(app.to_dict())
        
        return pipeline
    
    def get_pending_follow_ups(self) -> List[Dict]:
        """Get applications that need follow-up."""
        now = datetime.now()
        pending = []
        
        for app in self.applications.values():
            if (app.next_follow_up and 
                app.next_follow_up <= now and
                app.status not in [ApplicationStatus.REJECTED, 
                                   ApplicationStatus.OFFER_RECEIVED,
                                   ApplicationStatus.OFFER_ACCEPTED,
                                   ApplicationStatus.WITHDRAWN]):
                pending.append(app.to_dict())
        
        return sorted(pending, key=lambda x: x.get("next_follow_up", ""))
    
    def get_upcoming_interviews(self) -> List[Dict]:
        """Get upcoming interviews."""
        now = datetime.now()
        upcoming = []
        
        for app in self.applications.values():
            if (app.interview_date and 
                app.interview_date >= now and
                app.status == ApplicationStatus.INTERVIEW_SCHEDULED):
                upcoming.append(app.to_dict())
        
        return sorted(upcoming, key=lambda x: x.get("interview_date", ""))
    
    def get_analytics(self) -> Dict:
        """Get analytics and statistics."""
        total = len(self.applications)
        
        if total == 0:
            return {
                "total_applications": 0,
                "by_status": {},
                "by_portal": {},
                "response_rate": 0,
                "interview_rate": 0,
                "offer_rate": 0,
            }
        
        # Count by status
        by_status = {}
        for status in ApplicationStatus:
            count = sum(1 for app in self.applications.values() if app.status == status)
            if count > 0:
                by_status[status.value] = count
        
        # Count by portal
        by_portal = {}
        for app in self.applications.values():
            portal = app.portal or "unknown"
            by_portal[portal] = by_portal.get(portal, 0) + 1
        
        # Calculate rates
        applied = sum(1 for app in self.applications.values() 
                     if app.status.value in ["applied", "application_sent"])
        responded = sum(1 for app in self.applications.values()
                       if app.status.value in ["interview_scheduled", "interview_done", 
                                               "rejected", "offer_received"])
        interviewed = sum(1 for app in self.applications.values()
                         if app.status.value in ["interview_scheduled", "interview_done"])
        offers = sum(1 for app in self.applications.values()
                    if app.status.value in ["offer_received", "offer_accepted"])
        
        response_rate = (responded / applied * 100) if applied > 0 else 0
        interview_rate = (interviewed / applied * 100) if applied > 0 else 0
        offer_rate = (offers / applied * 100) if applied > 0 else 0
        
        # Average match score
        scores = [app.match_score for app in self.applications.values() if app.match_score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Time to response
        response_times = []
        for app in self.applications.values():
            if app.applied_at and app.status.value in ["interview_scheduled", "rejected"]:
                response_times.append((datetime.now() - app.applied_at).days)
        
        avg_response_days = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            "total_applications": total,
            "by_status": by_status,
            "by_portal": by_portal,
            "response_rate": round(response_rate, 1),
            "interview_rate": round(interview_rate, 1),
            "offer_rate": round(offer_rate, 1),
            "average_match_score": round(avg_score, 1),
            "average_response_days": round(avg_response_days, 1),
            "pending_follow_ups": len(self.get_pending_follow_ups()),
            "upcoming_interviews": len(self.get_upcoming_interviews()),
        }
    
    def get_daily_summary(self) -> Dict:
        """Get summary for today."""
        today = datetime.now().date()
        
        discovered_today = sum(1 for app in self.applications.values()
                              if app.discovered_at.date() == today)
        
        applied_today = sum(1 for app in self.applications.values()
                           if app.applied_at and app.applied_at.date() == today)
        
        interviews_today = sum(1 for app in self.applications.values()
                              if app.interview_date and app.interview_date.date() == today)
        
        return {
            "date": today.isoformat(),
            "discovered": discovered_today,
            "applied": applied_today,
            "interviews": interviews_today,
        }
    
    def get_best_performing(self, limit: int = 5) -> List[Dict]:
        """Get best performing portals/sources."""
        portal_stats = {}
        
        for app in self.applications.values():
            portal = app.portal or "unknown"
            if portal not in portal_stats:
                portal_stats[portal] = {
                    "portal": portal,
                    "total": 0,
                    "applied": 0,
                    "responses": 0,
                    "interviews": 0,
                    "offers": 0,
                }
            
            stats = portal_stats[portal]
            stats["total"] += 1
            
            if app.status.value in ["applied", "application_sent"]:
                stats["applied"] += 1
            elif app.status.value in ["interview_scheduled", "interview_done"]:
                stats["interviews"] += 1
            elif app.status.value in ["offer_received", "offer_accepted"]:
                stats["offers"] += 1
            elif app.status.value != "discovered":
                stats["responses"] += 1
        
        # Calculate response rates
        for stats in portal_stats.values():
            if stats["applied"] > 0:
                stats["response_rate"] = round(stats["responses"] / stats["applied"] * 100, 1)
            else:
                stats["response_rate"] = 0
        
        # Sort by response rate
        sorted_portals = sorted(portal_stats.values(), 
                               key=lambda x: x["response_rate"], 
                               reverse=True)
        
        return sorted_portals[:limit]


# Global tracker instance
_tracker: Optional[JobTracker] = None


def get_job_tracker() -> JobTracker:
    """Get the global job tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = JobTracker()
    return _tracker
