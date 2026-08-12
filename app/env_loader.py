from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_app_env() -> None:
    """Load project .env into process env without overriding exported vars."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
