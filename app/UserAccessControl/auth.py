"""Owner: C. Sign up, log in, and the session token. No web framework here: routes.py and the tests call these.

Customer sign-up is two steps: check_customer_id (is this ID in customers.csv and not signed up yet?), then sign_up
(create the password). The customer then logs in with their customer ID. Staff are seeded and only log in.

The token is stateless: base64(JSON {sub, role, exp}) + "." + HMAC-SHA256 signature. The key is AUTH_SECRET, or
a random one generated once into runtime/auth_secret (git-ignored), so tokens survive an API restart.
"""
import base64
import functools
import hashlib
import hmac
import json
import os
import secrets
import time

from app.UserAccessControl import accounts
from app.UserAccessControl.passwords import hash_password, verify_password
from app.UserAccessControl.roles import CUSTOMER

MIN_PASSWORD_LENGTH = 4
TOKEN_HOURS = float(os.environ.get("AUTH_TOKEN_HOURS", 8))
SECRET_FILE = accounts.ROOT / "runtime" / "auth_secret"


class AuthError(Exception):
    """A refusal the caller shows to the user: an HTTP status, a stable code for the frontend, and a message."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def check_customer_id(customer_id: str) -> accounts.Account:
    """Sign-up step 1: the ID must be a customer who has not signed up yet."""
    account = accounts.get_customer(customer_id)
    if account is None:
        raise AuthError(404, "NOT_A_CUSTOMER",
                        f"{customer_id.strip()} is not a Teratai Bank customer. Check your customer ID and try again.")
    if account.signed_up:
        raise AuthError(409, "ALREADY_SIGNED_UP", "This customer ID has already signed up. Please log in instead.")
    return account


def sign_up(customer_id: str, password: str) -> accounts.Account:
    """Sign-up step 2: create the customer's password. The customer then logs in."""
    account = check_customer_id(customer_id)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(422, "PASSWORD_TOO_SHORT", f"Use at least {MIN_PASSWORD_LENGTH} characters for your password.")
    try:
        accounts.set_customer_password(account.username, hash_password(password))
    except accounts.AlreadySignedUp:       # a second sign-up for the same ID got there first
        raise AuthError(409, "ALREADY_SIGNED_UP", "This customer ID has already signed up. Please log in instead.")
    return accounts.get_customer(account.username)


def login(username: str, password: str) -> tuple[str, accounts.Account]:
    """Staff username or customer ID, plus password. Returns (token, account)."""
    account = accounts.find(username)
    if account is not None and account.role == CUSTOMER and not account.signed_up:
        raise AuthError(403, "NOT_SIGNED_UP", "You haven't signed up yet. Please sign up first, then log in.")
    if account is None or not verify_password(password, account.password_hash):
        raise AuthError(401, "INVALID_CREDENTIALS", "Wrong username or password.")
    return issue_token(account), account


def issue_token(account: accounts.Account) -> str:
    payload = {"sub": account.username, "role": account.role, "exp": int(time.time() + TOKEN_HOURS * 3600)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_b64(_sign(body))}"


def user_from_token(token: str) -> accounts.Account:
    """The signed-in account. Looked up again on every request, so a removed account or changed role takes effect."""
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(_unb64(sig), _sign(body)):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        raise AuthError(401, "INVALID_TOKEN", "Your session is not valid. Please log in again.")
    if payload["exp"] < time.time():
        raise AuthError(401, "TOKEN_EXPIRED", "Your session has expired. Please log in again.")
    account = accounts.find(payload["sub"])
    if account is None or account.role != payload["role"] or not account.signed_up:
        raise AuthError(401, "INVALID_TOKEN", "Your session is not valid. Please log in again.")
    return account


def _sign(body: str) -> bytes:
    return hmac.new(_secret(), body.encode(), hashlib.sha256).digest()


@functools.lru_cache(maxsize=1)
def _secret() -> bytes:
    if os.environ.get("AUTH_SECRET"):
        return os.environ["AUTH_SECRET"].encode()
    if not SECRET_FILE.exists():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return SECRET_FILE.read_text(encoding="utf-8").strip().encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
