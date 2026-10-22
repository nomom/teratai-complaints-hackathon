"""Owner: C. User access control: four roles (officer, fraud, manager, customer), customer sign-up, login, and RBAC.

    roles.py      the roles and what each may see and do
    passwords.py  PBKDF2 password hashing
    accounts.py   accounts: data/staff.csv, and customer sign-ups in data/customer_accounts.csv
    auth.py       sign up, log in, session tokens
    deps.py       FastAPI dependencies: current_user, require_roles
    routes.py     the /auth endpoints
"""
