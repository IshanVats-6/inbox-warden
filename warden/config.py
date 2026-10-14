"""Runtime settings, read once from the environment (see .env.example)."""

import os
from dataclasses import dataclass


def _bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    public_url: str = os.environ.get("PUBLIC_URL", "http://localhost:8080").rstrip("/")
    data_dir: str = os.environ.get("DATA_DIR", "./data")
    admin_password: str = os.environ.get("ADMIN_PASSWORD", "")
    secret_key: str = os.environ.get("SECRET_KEY", "")
    demo_mode: bool = _bool("DEMO_MODE", False)

    # Google: an OAuth client (any Gmail / Workspace user signs in) and, optionally,
    # a service account with domain-wide delegation (Workspace admins adding many mailboxes)
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    google_service_account_file: str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")

    # Claude
    anthropic_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
    anthropic_effort: str = os.environ.get("ANTHROPIC_EFFORT", "low")
    batch_size: int = int(os.environ.get("BATCH_SIZE", "25"))

    # Agent
    schedule: str = os.environ.get("SCHEDULE", "0 7,14,19 * * *")
    timezone: str = os.environ.get("TZ", "UTC")
    max_emails_per_run: int = int(os.environ.get("MAX_EMAILS_PER_RUN", "500"))
    max_new_labels_per_run: int = int(os.environ.get("MAX_NEW_LABELS_PER_RUN", "15"))
    slack_webhook_url: str = os.environ.get("SLACK_WEBHOOK_URL", "")


settings = Settings()
