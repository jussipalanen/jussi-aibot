"""
Application settings read from environment variables.
"""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

LEGACY_REVIEW_PROVIDERS = {"default", "puter_ai", "vertex_ai", "gemini"}


def env(name: str, default: str = "") -> str:
    """Return a stripped environment variable, or the default when unset or blank."""
    value = os.getenv(name, "").strip()
    return value or default


def env_bool(name: str, default: bool = False) -> bool:
    """Return an environment variable parsed as a boolean."""
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """Return an environment variable parsed as an integer."""
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def env_list(name: str) -> list[str]:
    """Return a comma-separated environment variable as a list of non-empty items."""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the whole application."""

    app_name: str
    app_description: str
    config_dir: Path
    clients_file: Path | None
    default_rate_limit: str
    forwarded_ip_depth: int
    log_forwarded_for: bool
    max_upload_bytes: int
    review_provider: str
    legacy_review_provider: str
    legacy_puter_prompt_max_chars: int
    legacy_vertex_prompt_max_chars: int
    ai_secret_key: str
    allowed_origins: tuple[str, ...]
    demo_enabled: bool
    demo_public: bool
    demo_rate_limit: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the current environment."""
        config_dir = Path(env("CONFIG_DIR", str(BASE_DIR / "config")))
        clients_file_env = env("CLIENTS_FILE")
        if clients_file_env:
            clients_file: Path | None = Path(clients_file_env)
        elif (config_dir / "clients.yaml").is_file():
            clients_file = config_dir / "clients.yaml"
        else:
            clients_file = None

        legacy_provider = env("DEFAULT_PROVIDER", "default").lower()
        if legacy_provider not in LEGACY_REVIEW_PROVIDERS:
            raise ValueError(
                f"Invalid DEFAULT_PROVIDER '{legacy_provider}'. "
                f"Must be one of: {', '.join(sorted(LEGACY_REVIEW_PROVIDERS))}"
            )

        return cls(
            app_name=env("APP_NAME", "Jussi AI Bot"),
            app_description=env(
                "APP_DESCRIPTION",
                "A configurable AI agent platform: chat agents with tools and RAG, "
                "and document reviews, behind one API.",
            ),
            config_dir=config_dir,
            clients_file=clients_file,
            default_rate_limit=env("DAILY_RATE_LIMIT", "50/day"),
            forwarded_ip_depth=env_int("FORWARDED_IP_DEPTH", 0),
            log_forwarded_for=env_bool("LOG_FORWARDED_FOR"),
            max_upload_bytes=env_int("MAX_UPLOAD_MB", 50) * 1024 * 1024,
            review_provider=env("REVIEW_PROVIDER", "gemini").lower(),
            legacy_review_provider=legacy_provider,
            legacy_puter_prompt_max_chars=env_int("PUTER_PROMPT_MAX_CHARS", 6000),
            legacy_vertex_prompt_max_chars=env_int("VERTEX_PROMPT_MAX_CHARS", 6000),
            ai_secret_key=env("AI_SECRET_KEY"),
            allowed_origins=tuple(o.rstrip("/") for o in env_list("ALLOWED_ORIGINS")),
            demo_enabled=env_bool("DEMO_ENABLED", True),
            demo_public=env_bool("DEMO_PUBLIC"),
            demo_rate_limit=env("DEMO_RATE_LIMIT", "10/day"),
        )
