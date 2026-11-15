"""Passwords, session tokens and login throttling. No web framework code in here."""
import base64
import hashlib
import hmac
import secrets

# scrypt cost. About 32 MB and a few tens of milliseconds per check.
_N, _R, _P, _KEYLEN = 2 ** 15, 8, 1, 32
_MAXMEM = 128 * 1024 * 1024

MIN_PASSWORD = 12
MAX_PASSWORD = 200

# Failed sign-ins allowed inside the window before further tries are refused.
WINDOW_MINUTES = 15
MAX_FAILS_PER_EMAIL = 5
MAX_FAILS_PER_IP = 30


def _b64(raw):
    return base64.b64encode(raw).decode()


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEYLEN, maxmem=_MAXMEM)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(key)}"


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r),
                                p=int(p), dklen=len(expected), maxmem=_MAXMEM)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Checked when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_time(password):
    verify_password(password, _DUMMY_HASH)


def password_problem(password, email=""):
    """A sentence explaining why the password is not acceptable, or None if it is."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Use at most {MAX_PASSWORD} characters."
    if email and password.lower() == email.lower():
        return "Your password cannot be your email address."
    if len(set(password)) < 5:
        return "That password is too easy to guess."
    return None


def temp_password():
    return secrets.token_urlsafe(12)


def new_session_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def email_key(email):
    """Attempts are stored against a hash, so mistyped addresses are not kept in plain text."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def is_throttled(conn, email, ip):
    row = conn.execute(
        """SELECT
             count(*) FILTER (WHERE email_key = %(k)s) AS by_email,
             count(*) FILTER (WHERE ip = %(ip)s) AS by_ip
           FROM login_attempts
           WHERE NOT ok AND at > now() - make_interval(mins => %(w)s)
             AND (email_key = %(k)s OR ip = %(ip)s)""",
        {"k": email_key(email), "ip": ip, "w": WINDOW_MINUTES}).fetchone()
    return row["by_email"] >= MAX_FAILS_PER_EMAIL or row["by_ip"] >= MAX_FAILS_PER_IP


def record_attempt(conn, email, ip, ok):
    conn.execute("INSERT INTO login_attempts (email_key, ip, ok) VALUES (%s, %s, %s)",
                 (email_key(email), ip, ok))
    if ok:
        # A successful sign-in clears that address's failures.
        conn.execute("DELETE FROM login_attempts WHERE email_key = %s AND NOT ok", (email_key(email),))
