"""Configuration management for vision-guided scraping."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitConfig:
    """Rate limit settings for AI providers.
    
    NVIDIA: ~30 RPM (free tier, best for vision)
    Mistral: 2 RPM (limited free tier)
    Gemini: 15 RPM (free tier)
    """
    nvidia_rpm: int = 30
    mistral_rpm: int = 2
    gemini_rpm: int = 15
    window_seconds: int = 60


@dataclass
class BrowserConfig:
    """Browser settings."""
    headless: bool = False
    viewport_width: int = 1400
    viewport_height: int = 900
    navigation_timeout_ms: int = 30000


@dataclass
class NavigationConfig:
    """Navigation settings."""
    max_steps: int = 10
    step_wait_seconds: int = 1
    popup_retries: int = 3


@dataclass
class ExtractionConfig:
    """Extraction settings."""
    max_jobs_per_portal: int = 100
    max_scroll_attempts: int = 5
    scroll_wait_seconds: int = 2
    scroll_amount: int = 800


@dataclass
class ScrapingConfig:
    """Top-level configuration."""
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)

    @classmethod
    def from_env(cls) -> "ScrapingConfig":
        """Load configuration from environment variables."""
        return cls(
            rate_limit=RateLimitConfig(
                nvidia_rpm=int(os.getenv("VISION_NVIDIA_RPM", "30")),
                mistral_rpm=int(os.getenv("VISION_MISTRAL_RPM", "2")),
                gemini_rpm=int(os.getenv("VISION_GEMINI_RPM", "15")),
            ),
            browser=BrowserConfig(
                headless=os.getenv("VISION_HEADLESS", "false").lower() == "true",
                viewport_width=int(os.getenv("VIEWPORT_WIDTH", "1400")),
                viewport_height=int(os.getenv("VIEWPORT_HEIGHT", "900")),
            ),
            navigation=NavigationConfig(
                max_steps=int(os.getenv("VISION_MAX_STEPS", "10")),
                popup_retries=int(os.getenv("VISION_POPUP_RETRIES", "3")),
            ),
            extraction=ExtractionConfig(
                max_jobs_per_portal=int(os.getenv("VISION_MAX_JOBS", "100")),
                max_scroll_attempts=int(os.getenv("VISION_MAX_SCROLLS", "5")),
            ),
        )

    def validate(self) -> list:
        """Validate configuration. Returns list of errors."""
        errors = []
        if self.rate_limit.nvidia_rpm <= 0:
            errors.append("nvidia_rpm must be positive")
        if self.rate_limit.mistral_rpm <= 0:
            errors.append("mistral_rpm must be positive")
        if self.rate_limit.gemini_rpm <= 0:
            errors.append("gemini_rpm must be positive")
        if self.browser.viewport_width <= 0:
            errors.append("viewport_width must be positive")
        if self.browser.viewport_height <= 0:
            errors.append("viewport_height must be positive")
        if self.navigation.max_steps <= 0:
            errors.append("max_steps must be positive")
        if self.extraction.max_jobs_per_portal <= 0:
            errors.append("max_jobs_per_portal must be positive")
        if self.extraction.max_scroll_attempts <= 0:
            errors.append("max_scroll_attempts must be positive")
        return errors
