"""
Configuration management for Cold Outreach Copilot
Centralized config with environment variable support
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class LLMConfig:
    """LLM (Large Language Model) configuration"""
    model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))


@dataclass
class ScraperConfig:
    """Web scraper configuration"""
    rate_limit: float = float(os.getenv("SCRAPER_RATE_LIMIT", "2.0"))
    timeout: int = int(os.getenv("SCRAPER_TIMEOUT", "15000"))  # Reduced from 30s to 15s for better UX
    cache_dir: str = os.getenv("SCRAPER_CACHE_DIR", "data/scraped_content")
    cache_enabled: bool = os.getenv("SCRAPER_CACHE_ENABLED", "true").lower() == "true"
    min_content_length: int = int(os.getenv("MIN_CONTENT_LENGTH", "200"))
    max_retries: int = int(os.getenv("SCRAPER_MAX_RETRIES", "2"))
    js_rendering: bool = os.getenv("SCRAPER_JS_RENDERING", "true").lower() == "true"
    js_wait_time: int = int(os.getenv("SCRAPER_JS_WAIT_TIME", "3000"))


@dataclass
class GuardrailsConfig:
    """Message quality guardrails configuration"""
    min_citations: int = int(os.getenv("MIN_CITATIONS", "2"))
    max_word_count: int = int(os.getenv("MAX_WORD_COUNT", "200"))
    min_approval_score: float = float(os.getenv("MIN_APPROVAL_SCORE", "0.9"))
    min_revision_score: float = float(os.getenv("MIN_REVISION_SCORE", "0.6"))
    min_appropriateness_score: float = float(os.getenv("MIN_APPROPRIATENESS_SCORE", "7.0"))


@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str = os.getenv("DATABASE_PATH", "data/outreach.db")
    echo: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"


@dataclass
class FollowUpConfig:
    """Follow-up scheduling configuration"""
    auto_schedule: bool = os.getenv("AUTO_SCHEDULE_FOLLOWUPS", "true").lower() == "true"
    default_days: int = int(os.getenv("DEFAULT_FOLLOWUP_DAYS", "7"))


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = os.getenv("LOG_LEVEL", "INFO")
    file_path: Optional[str] = os.getenv("LOG_FILE_PATH", "data/app.log")
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Config:
    """Main configuration container"""

    def __init__(self):
        self.llm = LLMConfig()
        self.scraper = ScraperConfig()
        self.guardrails = GuardrailsConfig()
        self.database = DatabaseConfig()
        self.followup = FollowUpConfig()
        self.logging = LoggingConfig()

    def __repr__(self):
        return (
            f"Config(\n"
            f"  llm={self.llm},\n"
            f"  scraper={self.scraper},\n"
            f"  guardrails={self.guardrails},\n"
            f"  database={self.database},\n"
            f"  followup={self.followup},\n"
            f"  logging={self.logging}\n"
            f")"
        )


# Global config instance
config = Config()


# Helper functions
def get_config() -> Config:
    """Get the global configuration instance"""
    return config


def reload_config():
    """Reload configuration from environment variables"""
    global config
    load_dotenv(override=True)
    config = Config()
