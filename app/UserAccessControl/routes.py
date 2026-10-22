"""Owner: C. The /auth endpoints. Mounted by app/api.py.

    POST /auth/signup/verify   {customer_id}             step 1: is this a customer who hasn't signed up?
    POST /auth/signup          {customer_id, password}   step 2: create the password, then go to the login page
    POST /auth/login           {username, password}      staff username or customer ID -> bearer token
    GET  /auth/me                                        the signed-in account

Error codes the frontend should handle: NOT_A_CUSTOMER (404), ALREADY_SIGNED_UP (409), PASSWORD_TOO_SHORT (422),
NOT_SIGNED_UP (403, on login: send the user to sign up), INVALID_CREDENTIALS (401).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.UserAccessControl import auth
from app.UserAccessControl.accounts import Account
from app.UserAccessControl.deps import current_user, http_error

router = APIRouter(prefix="/auth", tags=["auth"])


class CustomerIdIn(BaseModel):
    customer_id: str


class SignUpIn(BaseModel):
    customer_id: str
    password: str


class LoginIn(BaseModel):
    username: str           # staff username (e.g. officer1) or customer ID (e.g. CUS-00150)
    password: str


@router.post("/signup/verify")
def signup_verify(body: CustomerIdIn):
    try:
        account = auth.check_customer_id(body.customer_id)
    except auth.AuthError as e:
        raise http_error(e)
    return {"customer_id": account.username, "next": "create_password"}


@router.post("/signup", status_code=201)
def signup(body: SignUpIn):
    try:
        account = auth.sign_up(body.customer_id, body.password)
    except auth.AuthError as e:
        raise http_error(e)
    return {"customer_id": account.username, "next": "login", "message": "Signed up. Please log in."}


@router.post("/login")
def login(body: LoginIn):
    try:
        token, account = auth.login(body.username, body.password)
    except auth.AuthError as e:
        raise http_error(e)
    return {"access_token": token, "token_type": "bearer", "expires_in": int(auth.TOKEN_HOURS * 3600),
            "user": account.public()}


@router.get("/me")
def me(user: Account = Depends(current_user)):
    return user.public()
