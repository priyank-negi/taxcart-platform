"""Database schema and connection helper."""
import psycopg
from psycopg.rows import dict_row

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      is_staff BOOLEAN NOT NULL DEFAULT false,
      must_change_password BOOLEAN NOT NULL DEFAULT true,
      disabled BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_login_at TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS tenants (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS tenant_members (
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY (tenant_id, user_id))""",
    # Where a client's sales data comes from. Phase 1: a Shopify store.
    """CREATE TABLE IF NOT EXISTS tenant_sources (
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      kind TEXT NOT NULL CHECK (kind IN ('shopify')),
      ref TEXT NOT NULL,
      PRIMARY KEY (tenant_id, kind))""",
    # The countries staff have chosen for a client, and which are reported region by region.
    """CREATE TABLE IF NOT EXISTS tenant_countries (
      tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
      country CHAR(2) NOT NULL,
      split_by_region BOOLEAN NOT NULL DEFAULT false,
      PRIMARY KEY (tenant_id, country))""",
    # Only a hash of the session token is stored, so a database leak cannot be replayed.
    """CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS login_attempts (
      id BIGSERIAL PRIMARY KEY,
      email_key TEXT NOT NULL,
      ip TEXT,
      at TIMESTAMPTZ NOT NULL DEFAULT now(),
      ok BOOLEAN NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS login_attempts_email_at ON login_attempts (email_key, at)",
    "CREATE INDEX IF NOT EXISTS login_attempts_ip_at ON login_attempts (ip, at)",
    """CREATE TABLE IF NOT EXISTS audit_log (
      id BIGSERIAL PRIMARY KEY,
      at TIMESTAMPTZ NOT NULL DEFAULT now(),
      actor_user_id UUID,
      action TEXT NOT NULL,
      detail JSONB NOT NULL DEFAULT '{}'::jsonb)""",
]


# Columns added after the tables first shipped.
ADDED_COLUMNS = [
    # The currency the country's return is filed in. NULL means the store's own currency.
    "ALTER TABLE tenant_countries ADD COLUMN IF NOT EXISTS filing_currency CHAR(3)",
]


def connect(database_url):
    return psycopg.connect(database_url, row_factory=dict_row)


def migrate(database_url):
    with connect(database_url) as conn:
        for statement in SCHEMA + ADDED_COLUMNS:
            conn.execute(statement)
