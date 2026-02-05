from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General
    ENV: str = "development"
    BASE_PUBLIC_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "unsafe_default_secret"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    DB_PATH: str = "daily_agent.db"
    DATABASE_URL: str | None = None

    ALLOWED_HOSTS: str = "*"
    CORS_ORIGINS: str = ""

    # Scheduler
    SCHEDULE_HOUR: int = 9
    SCHEDULE_MINUTE: int = 0
    TIMEZONE: str = "Europe/Amsterdam"

    # Queue
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # Auth
    BASIC_AUTH_USER: str | None = None
    BASIC_AUTH_PASS: str | None = None
    ADMIN_USERNAME: str | None = None
    ADMIN_PASSWORD: str | None = None
    SESSION_TTL_HOURS: int = 24
    RATE_LIMIT_AUTH_PER_MIN: int = 10
    RATE_LIMIT_ACTION_PER_MIN: int = 60

    # Collection
    GIT_REPO_PATH: str = "."
    DEVLOG_PATH: str = "devlog.md"
    SENSITIVE_WORDS: str = "password,secret,token,api_key"

    # LLM
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Twitter
    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_ACCESS_TOKEN: str = ""
    TWITTER_ACCESS_TOKEN_SECRET: str = ""
    DRY_RUN: bool = True

    # V2 Controls
    TOKEN_TTL_HOURS: int = 36
    REWRITE_MAX: int = 1
    SIMILARITY_THRESHOLD: float = 0.6
    METRICS_ENABLED: bool = True
    METRICS_PATH: str = "/metrics"
    METRICS_INCLUDE_DB: bool = True
    BLOCKED_TERMS_PATH: str = "./blocked_terms.yaml"

    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "daily-x-agent"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_EXPORTER_OTLP_HEADERS: str = ""
    OTEL_TRACES_SAMPLER_RATIO: float = 0.1

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # Sources (plugins)
    ENABLE_SOURCE_NOTION: bool = False
    ENABLE_SOURCE_GITHUB: bool = False
    ENABLE_SOURCE_RSS: bool = False
    NOTION_API_KEY: str = ""
    NOTION_DB_ID: str = ""
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = ""
    RSS_FEED_URLS: str = ""

    # Thread
    THREAD_ENABLED: bool = False
    THREAD_MAX_TWEETS: int = 5
    THREAD_NUMBERING_ENABLED: bool = True

    # Style weekly update
    STYLE_UPDATE_WEEKDAY: int = 1
    STYLE_UPDATE_HOUR: int = 9
    STYLE_INPUT_POSTS: int = 30

    # Weekly report
    WEEKLY_REPORT_WEEKDAY: int = 1
    WEEKLY_REPORT_HOUR: int = 10

    # Email
    EMAIL_PROVIDER: str = "smtp"  # sendgrid or smtp
    SENDGRID_API_KEY: str | None = None
    SMTP_SERVER: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str = "daily-agent@example.com"
    EMAIL_TO: str = "me@example.com"

    # Slack
    ENABLE_SLACK: bool = False
    SLACK_WEBHOOK_URL: str | None = None

    # WhatsApp
    ENABLE_WHATSAPP: bool = False
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None
    TWILIO_TO_NUMBER: str | None = None

    # Policy v3 controls
    POLICY_LLM_CLAIMS_ENABLED: bool = False
    POLICY_LLM_CLAIMS_MODEL: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sensitive_words_list(self) -> list[str]:
        return [w.strip() for w in self.SENSITIVE_WORDS.split(",") if w.strip()]


settings = Settings()
