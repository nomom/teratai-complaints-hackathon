"""Owner: C. FastAPI dependencies: who is calling, and are they allowed.

    @app.get("/stats")
    def stats(user=Depends(require_roles(MANAGER))): ...

Clients send  Authorization: Bearer <token>  (from POST /auth/login). The Swagger page's "Authorize" button does it too.
Errors come back as {"detail": {"code": ..., "message": ...}} so the frontend can branch on the code.
"""
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.UserAccessControl import auth
from app.UserAccessControl.accounts import Account

_bearer = HTTPBearer(auto_error=False)


def http_error(e: auth.AuthError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "message": e.message},
                         headers={"WWW-Authenticate": "Bearer"} if e.status == 401 else None)


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Account:
    if creds is None:
        raise http_error(auth.AuthError(401, "NOT_LOGGED_IN", "Please log in."))
    try:
        return auth.user_from_token(creds.credentials)
    except auth.AuthError as e:
        raise http_error(e)


def optional_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Optional[Account]:
    """The signed-in user, or None when the call carries no token (the organisers' contract calls carry none).
    A token that is sent but invalid is still a 401: it never quietly counts as "not logged in"."""
    return None if creds is None else current_user(creds)


def require_roles(*roles: str):
    """A dependency that lets through only these roles (403 for any other signed-in role)."""
    def dependency(user: Account = Depends(current_user)) -> Account:
        if user.role not in roles:
            raise HTTPException(403, {"code": "FORBIDDEN", "message": f"Your role ({user.role}) cannot do this."})
        return user
    return dependency
