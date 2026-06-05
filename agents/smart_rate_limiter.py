"""Smart Rate Limiter - Prevent portal bans and manage request quotas.

Features:
- Per-portal rate limiting (minute/hour)
- Adaptive backoff on errors
- Request queuing
- Statistics tracking
"""
import time
import asyncio
from collections import defaultdict
from typing import Dict, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class PortalRateState:
    """Rate limiting state for a single portal."""
    requests_minute: int = 0
    requests_hour: int = 0
    last_minute_reset: float = 0
    last_hour_reset: float = 0
    
    # Adaptive backoff
    consecutive_errors: int = 0
    last_error_time: float = 0
    cooldown_until: float = 0
    
    # Statistics
    total_requests: int = 0
    total_errors: int = 0
    total_blocked: int = 0


class SmartRateLimiter:
    """Intelligent rate limiter with adaptive backoff."""
    
    def __init__(self):
        self._states: Dict[str, PortalRateState] = defaultdict(PortalRateState)
        self._lock = asyncio.Lock()
    
    def _get_state(self, portal: str) -> PortalRateState:
        """Get or create rate state for a portal."""
        return self._states[portal]
    
    def _reset_minute_if_needed(self, state: PortalRateState):
        """Reset minute counter if a minute has passed."""
        now = time.time()
        if now - state.last_minute_reset >= 60:
            state.requests_minute = 0
            state.last_minute_reset = now
    
    def _reset_hour_if_needed(self, state: PortalRateState):
        """Reset hour counter if an hour has passed."""
        now = time.time()
        if now - state.last_hour_reset >= 3600:
            state.requests_hour = 0
            state.last_hour_reset = now
    
    async def wait_if_needed(self, portal: str, rate_limit_minute: int = 10, rate_limit_hour: int = 100) -> float:
        """Wait if rate limit would be exceeded. Returns wait time (0 if no wait needed)."""
        async with self._lock:
            state = self._get_state(portal)
            now = time.time()
            
            # Check if in cooldown from errors
            if state.cooldown_until > now:
                wait_time = state.cooldown_until - now
                logger.info(f"[{portal}] In cooldown, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                return wait_time
            
            # Reset counters if needed
            self._reset_minute_if_needed(state)
            self._reset_hour_if_needed(state)
            
            wait_time = 0
            
            # Check minute limit
            if state.requests_minute >= rate_limit_minute:
                wait_time = max(wait_time, 60 - (now - state.last_minute_reset))
                logger.info(f"[{portal}] Minute limit reached ({state.requests_minute}/{rate_limit_minute}), waiting {wait_time:.1f}s")
            
            # Check hour limit
            if state.requests_hour >= rate_limit_hour:
                hour_wait = 3600 - (now - state.last_hour_reset)
                wait_time = max(wait_time, hour_wait)
                logger.info(f"[{portal}] Hour limit reached ({state.requests_hour}/{rate_limit_hour}), waiting {hour_wait:.1f}s")
            
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            # Increment counters
            state.requests_minute += 1
            state.requests_hour += 1
            state.total_requests += 1
            
            return wait_time
    
    async def record_success(self, portal: str):
        """Record a successful request."""
        async with self._lock:
            state = self._get_state(portal)
            state.consecutive_errors = 0
    
    async def record_error(self, portal: str, is_blocked: bool = False):
        """Record a failed request. Applies adaptive backoff."""
        async with self._lock:
            state = self._get_state(portal)
            now = time.time()
            
            state.total_errors += 1
            state.last_error_time = now
            state.consecutive_errors += 1
            
            if is_blocked:
                state.total_blocked += 1
                # Aggressive backoff for blocks
                cooldown = min(300, 30 * (2 ** min(state.consecutive_errors - 1, 4)))  # Max 5 min
                state.cooldown_until = now + cooldown
                logger.warning(f"[{portal}] BLOCKED! Cooling down for {cooldown:.0f}s (consecutive errors: {state.consecutive_errors})")
            elif state.consecutive_errors >= 3:
                # Exponential backoff after 3 consecutive errors
                cooldown = min(60, 5 * (2 ** min(state.consecutive_errors - 3, 3)))  # Max 1 min
                state.cooldown_until = now + cooldown
                logger.warning(f"[{portal}] {state.consecutive_errors} consecutive errors, cooling down for {cooldown:.0f}s")
    
    def can_request(self, portal: str, rate_limit_minute: int = 10, rate_limit_hour: int = 100) -> bool:
        """Check if a request can be made without waiting."""
        state = self._get_state(portal)
        now = time.time()
        
        # Check cooldown
        if state.cooldown_until > now:
            return False
        
        # Check minute limit
        self._reset_minute_if_needed(state)
        if state.requests_minute >= rate_limit_minute:
            return False
        
        # Check hour limit
        self._reset_hour_if_needed(state)
        if state.requests_hour >= rate_limit_hour:
            return False
        
        return True
    
    def get_stats(self) -> Dict[str, Dict]:
        """Get rate limiting statistics for all portals."""
        stats = {}
        for portal, state in self._states.items():
            stats[portal] = {
                "requests_minute": state.requests_minute,
                "requests_hour": state.requests_hour,
                "total_requests": state.total_requests,
                "total_errors": state.total_errors,
                "total_blocked": state.total_blocked,
                "consecutive_errors": state.consecutive_errors,
                "in_cooldown": state.cooldown_until > time.time(),
                "cooldown_remaining": max(0, state.cooldown_until - time.time()),
            }
        return stats
    
    def reset_portal(self, portal: str):
        """Reset rate state for a portal."""
        self._states[portal] = PortalRateState()
        logger.info(f"Reset rate state for {portal}")


# Global rate limiter instance
_rate_limiter: Optional[SmartRateLimiter] = None


def get_rate_limiter() -> SmartRateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SmartRateLimiter()
    return _rate_limiter
