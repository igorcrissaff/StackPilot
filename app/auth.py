import secrets
from fastapi import HTTPException, Request, status


def require_auth(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def verify_credentials(username: str, password: str, expected_user: str, expected_password: str) -> bool:
    user_ok = secrets.compare_digest(username.encode("utf-8"), expected_user.encode("utf-8"))
    pass_ok = secrets.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    return user_ok and pass_ok
