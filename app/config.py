import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # General
    ENV: str = "development"
    BASE_PUBLIC_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "unsafe_default_secret"
    LOG_LEVEL: str = "INFO"

    # Scheduler
    SCHEDULE_HOUR: int = 9
    SCHEDULE_MINUTE: int = 0
    TIMEZONE: str = "Europe/Amsterdam"

    # Auth
    BASIC_AUTH_USER: Optional[str] = None
    BASIC_AUTH_PASS: Optional[str] = None

    # Collection
    GIT_REPO_PATH: str = "."
    DEVLOG_PATH: str = "devlog.md"
    SENSITIVE_WORDS: str = "password,secret,token,api_key"

    # LLM
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Twitter
    TWITTER_API_KEY: str
    TWITTER_API_SECRET: str
    TWITTER_ACCESS_TOKEN: str
    TWITTER_ACCESS_TOKEN_SECRET: str
    DRY_RUN: bool = True

    # Email
    EMAIL_PROVIDER: str = "smtp"  # sendgrid or smtp
    SENDGRID_API_KEY: Optional[str] = None
    SMTP_SERVER: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str = "daily-agent@example.com"
    EMAIL_TO: str = "me@example.com"

    # WhatsApp
    ENABLE_WHATSAPP: bool = False
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None
    TWILIO_TO_NUMBER: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def sensitive_words_list(self) -> List[str]:
        return [w.strip() for w in self.SENSITIVE_WORDS.split(",") if w.strip()]

settings = Settings()
