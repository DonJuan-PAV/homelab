"""
Settings, read from the .env file. Each mailbox is optional:
fill in Outlook, Gmail, or both.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Settings:
    outlook_client_id: str     # Azure app ID (empty = Outlook turned off)
    outlook_focused_only: bool # only count Outlook's "Focused" inbox
    gmail_address: str         # empty = Gmail turned off
    gmail_app_password: str
    gmail_search: str          # Gmail search used to find new mail
    poll_seconds: int
    data_dir: str
    stats_host: str
    stats_port: int


def _as_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        outlook_client_id=os.getenv("OUTLOOK_CLIENT_ID", "").strip(),
        outlook_focused_only=_as_bool(os.getenv("OUTLOOK_FOCUSED_ONLY", "false")),
        gmail_address=os.getenv("GMAIL_ADDRESS", "").strip(),
        # Google shows the app password with spaces; they're not part of it
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
        gmail_search=os.getenv("GMAIL_SEARCH", "").strip(),
        poll_seconds=int(os.getenv("POLL_SECONDS", "60")),
        data_dir=os.getenv("DATA_DIR", "data").strip(),
        stats_host=os.getenv("STATS_HOST", "0.0.0.0").strip(),
        stats_port=int(os.getenv("STATS_PORT", "8080")),
    )


def validate(settings: Settings) -> list[str]:
    problems = []
    if not settings.outlook_client_id and not settings.gmail_address:
        problems.append("No mailbox configured: set OUTLOOK_CLIENT_ID and/or GMAIL_ADDRESS.")
    if settings.gmail_address and not settings.gmail_app_password:
        problems.append("GMAIL_APP_PASSWORD is required when GMAIL_ADDRESS is set.")
    if settings.poll_seconds < 15:
        problems.append("POLL_SECONDS must be at least 15 (Gmail limits frequent logins).")
    return problems
