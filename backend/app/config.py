"""Explicit server configuration. No implicit .env reads or client-side secrets."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///data/infinite_stories.sqlite3"
    environment: str = "development"
    allowed_origins: tuple[str, ...] = ("http://localhost:8080", "http://127.0.0.1:8080")
    session_days: int = 30
    requests_per_minute: int = 120
    qloo_key: str = field(default="", repr=False)
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    qloo_calls_allowed: bool = False
    qloo_daily_requests: int = 100
    qloo_cache_seconds: int = 3600
    qloo_min_interval: float = 1.0
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_provider: str = ""
    llm_model: str = ""
    llm_key: str = field(default="", repr=False)
    llm_reasoning_effort: str = ""
    llm_calls_allowed: bool = False
    llm_turn_limit: int = 20
    llm_daily_turn_limit: int = 20

    def validate(self):
        if not 1 <= self.session_days <= 90 or not 1 <= self.requests_per_minute <= 1000:
            raise ValueError("Invalid session or request limit")
        if not 1 <= self.llm_turn_limit <= 50:
            raise ValueError("Invalid model turn limit")
        if not 1 <= self.llm_daily_turn_limit <= 1000:
            raise ValueError("Invalid daily model turn limit")
        if self.environment not in ("development", "test", "production"):
            raise ValueError("Unknown application environment")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or "*" in origin
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS requires exact HTTP origins without paths or credentials")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL with the psycopg driver")
            if not self.allowed_origins or any(not o.startswith("https://") for o in self.allowed_origins):
                raise ValueError("Production requires explicit HTTPS client origins")
        if self.qloo_base_url != "https://hackathon.api.qloo.com":
            raise ValueError("Qloo hackathon origin must match the verified host exactly")
        if (
            not 1 <= self.qloo_daily_requests <= 10000
            or not 0 <= self.qloo_cache_seconds <= 86400
            or not 0 <= self.qloo_min_interval <= 60
        ):
            raise ValueError("Invalid Qloo application budget/cache/pacing")
        if self.qloo_calls_allowed and (not self.qloo_key or self.qloo_key.startswith(("REPLACE_", "YOUR_"))):
            raise ValueError("Authorized Qloo calls require a private server credential")
        if self.llm_provider not in ("", "openai", "ollama"):
            raise ValueError("Unsupported model adapter")
        if self.llm_reasoning_effort not in ("", "none", "low", "medium", "high", "xhigh", "max"):
            raise ValueError("Unknown model reasoning effort")
        if self.llm_provider == "ollama":
            if self.llm_base_url != "http://127.0.0.1:11434":
                raise ValueError("Local inference requires the fixed loopback origin")
            if not self.llm_model or ":" not in self.llm_model or any(x in self.llm_model for x in ("cloud", "/", "@")):
                raise ValueError("Local inference requires an explicit local model tag")
        if self.llm_calls_allowed and not (
            self.llm_provider and self.llm_model and (self.llm_key or self.llm_provider == "ollama")
        ):
            raise ValueError("Authorized model calls require provider, model and server key")
        if self.llm_calls_allowed and self.llm_provider != "ollama" and self.llm_key.startswith(("REPLACE_", "YOUR_")):
            raise ValueError("Placeholder credentials cannot authorize model calls")
        return self

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            database_url=os.getenv("IS_DATABASE_URL", defaults.database_url),
            environment=os.getenv("IS_ENVIRONMENT", defaults.environment),
            allowed_origins=tuple(
                x.strip()
                for x in os.getenv("IS_ALLOWED_ORIGINS", ",".join(defaults.allowed_origins)).split(",")
                if x.strip()
            ),
            session_days=int(os.getenv("IS_SESSION_DAYS", "30")),
            requests_per_minute=int(os.getenv("IS_REQUESTS_PER_MINUTE", "120")),
            qloo_key=os.getenv("QLOO_API_KEY", ""),
            qloo_base_url=os.getenv("QLOO_BASE_URL", defaults.qloo_base_url),
            qloo_calls_allowed=os.getenv("IS_QLOO_CALLS_ALLOWED", "false").lower() == "true",
            qloo_daily_requests=int(os.getenv("IS_QLOO_DAILY_REQUESTS", "100")),
            qloo_cache_seconds=int(os.getenv("IS_QLOO_CACHE_SECONDS", "3600")),
            qloo_min_interval=float(os.getenv("IS_QLOO_MIN_INTERVAL", "1")),
            llm_base_url=os.getenv("IS_LLM_BASE_URL", defaults.llm_base_url),
            llm_provider=os.getenv("IS_LLM_PROVIDER", ""),
            llm_model=os.getenv("IS_LLM_MODEL", ""),
            llm_key=os.getenv("IS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            llm_reasoning_effort=os.getenv("IS_LLM_REASONING_EFFORT", ""),
            llm_calls_allowed=os.getenv("IS_LLM_CALLS_ALLOWED", "false").lower() == "true",
            llm_turn_limit=int(os.getenv("IS_LLM_TURN_LIMIT", "20")),
            llm_daily_turn_limit=int(os.getenv("IS_LLM_DAILY_TURN_LIMIT", "20")),
        ).validate()
