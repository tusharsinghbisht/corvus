import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException

from .database import audit

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def cookie_name(settings):
    return "__Host-corvus_session" if settings.secure else "corvus_session"


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(db, token):
    if not token or len(token) > 128:
        raise HTTPException(401, "Sign in to access the workspace")
    user = db.execute(
        """
        SELECT u.id,u.username FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=%s AND s.expires_at>now()
    """,
        (digest(token),),
    ).fetchone()
    if not user:
        raise HTTPException(401, "Session expired; sign in again")
    return user


def sign_in(db, username, password):
    # Serialize attempts so parallel logins cannot bypass the pilot's global throttle.
    db.execute("SELECT pg_advisory_xact_lock(hashtext('corvus.login'))")
    db.execute("DELETE FROM login_failures WHERE at<now()-interval '15 minutes'")
    if db.execute("SELECT count(*) AS n FROM login_failures").fetchone()["n"] >= 10:
        return None, "throttled"
    user = db.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()
    try:
        valid = HASHER.verify(user["password_hash"] if user else DUMMY_HASH, password)
    except VerificationError:
        valid = False
    if not user or not valid:
        db.execute("INSERT INTO login_failures DEFAULT VALUES")
        return None, "invalid"
    token = secrets.token_urlsafe(48)
    db.execute("DELETE FROM sessions WHERE expires_at<=now()")
    db.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,now()+interval '12 hours')",
        (digest(token), user["id"]),
    )
    audit(db, "session.created", user_id=user["id"])
    return token, None
