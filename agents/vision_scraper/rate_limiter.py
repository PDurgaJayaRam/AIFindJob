"""Rate limiter for managing AI provider API calls."""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ProviderRateLimit:
    """Rate limit configuration for a provider."""
    max_requests: int
    window_seconds: int = 60


class RateLimiter:
    """Manages rate limits for multiple AI providers using sliding window."""

    def __init__(self):
        # NVIDIA has much higher rate limits (no hard limit published, conservative estimate)
        # From testing: NVIDIA allows ~20-30 RPM for vision models
        self._providers: Dict[str, ProviderRateLimit] = {
            "nvidia": ProviderRateLimit(max_requests=30, window_seconds=60),
            "mistral": ProviderRateLimit(max_requests=2, window_seconds=60),
            "gemini": ProviderRateLimit(max_requests=15, window_seconds=60),
        }
        self._states: Dict[str, List[float]] = {
            name: [] for name in self._providers
        }

    def configure_provider(self, name: str, max_requests: int, window_seconds: int = 60):
        """Configure or update rate limits for a provider."""
        self._providers[name] = ProviderRateLimit(
            max_requests=max_requests, window_seconds=window_seconds
        )
        if name not in self._states:
            self._states[name] = []

    def _clean_old_requests(self, provider: str):
        """Remove requests outside the current sliding window."""
        state = self._states[provider]
        config = self._providers[provider]
        cutoff = time.time() - config.window_seconds
        self._states[provider] = [ts for ts in state if ts > cutoff]

    def check_availability(self, provider: str) -> bool:
        """Check if a provider can accept a new request."""
        if provider not in self._providers:
            return False
        self._clean_old_requests(provider)
        state = self._states[provider]
        config = self._providers[provider]
        return len(state) < config.max_requests

    def record_request(self, provider: str):
        """Record a request for a provider."""
        if provider not in self._states:
            raise ValueError(f"Unknown provider: {provider}")
        self._states[provider].append(time.time())

    def wait_for_capacity(self, provider: str) -> float:
        """Calculate wait time until capacity is available. Returns seconds to wait."""
        if provider not in self._providers:
            return 0.0
        self._clean_old_requests(provider)
        state = self._states[provider]
        config = self._providers[provider]
        if len(state) < config.max_requests:
            return 0.0
        oldest = min(state)
        wait_time = (oldest + config.window_seconds) - time.time()
        return max(0.0, wait_time)

    def get_next_available_provider(self) -> Optional[str]:
        """Get the next provider that has capacity, prioritizing nvidia then mistral then gemini."""
        # Priority: NVIDIA (30 RPM) > Mistral (2 RPM) > Gemini (15 RPM)
        priority_order = ["nvidia", "mistral", "gemini"]
        for provider in priority_order:
            if provider in self._providers and self.check_availability(provider):
                return provider
        for provider in self._providers:
            if provider not in priority_order and self.check_availability(provider):
                return provider
        return None

    def get_rate_limit_status(self) -> Dict[str, Dict]:
        """Get current rate limit status for all providers."""
        status = {}
        for provider in self._providers:
            self._clean_old_requests(provider)
            state = self._states[provider]
            config = self._providers[provider]
            used = len(state)
            status[provider] = {
                "used": used,
                "limit": config.max_requests,
                "window_seconds": config.window_seconds,
                "available": config.max_requests - used,
                "wait_time_seconds": self.wait_for_capacity(provider),
            }
        return status
