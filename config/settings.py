"""Application settings loaded from environment variables."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Combo AI Agent"
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg2://career_agent:career_agent@localhost:5432/career_agent"
    REDIS_URL: str = "redis://localhost:6379/0"

    OPENAI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    PRIMARY_AI_PROVIDER: str = "nvidia"

    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_SLOW_MO: int = 500

    REQUEST_TIMEOUT: int = 30
    RATE_LIMIT_DELAY: int = 2

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    DEFAULT_CITY: str = "Hyderabad"
    DEFAULT_SKILLS: str = "Python,SQL,Data Analysis"
    BROWSER_PROXY: str = ""  # Residential proxy for Cloudflare-blocked sites

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
