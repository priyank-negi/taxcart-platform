"""Settings, read once from environment variables. Secrets never live in code or the database."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    engine_url: str
    engine_key: str
    origins: tuple
    session_days: int
    cookie_secure: bool
    bootstrap_email: str
    bootstrap_password: str


def load():
    origins = tuple(o.strip().rstrip("/") for o in _required("APP_ORIGIN").split(",") if o.strip())
    for origin in origins:
        local = origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
        if not (origin.startswith("https://") or local):
            raise RuntimeError("APP_ORIGIN must be https (http is allowed for localhost only)")
    return Settings(
        database_url=_required("DATABASE_URL"),
        engine_url=_required("TAX_ENGINE_URL").rstrip("/"),
        engine_key=_required("TAX_ENGINE_KEY"),
        origins=origins,
        session_days=int(os.environ.get("SESSION_DAYS", "7")),
        # Cookies are sent over https only, unless every origin is localhost.
        cookie_secure=any(o.startswith("https://") for o in origins),
        bootstrap_email=os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower(),
        bootstrap_password=os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", ""),
    )
