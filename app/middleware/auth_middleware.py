from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.config import settings

bearer_scheme = HTTPBearer(auto_error=True)

# Tokens are issued elsewhere (shell/auth service) and have been observed signed with
# HS512, while this service historically only allowed HS256 — an HS512 token then fails
# decode with "alg not allowed" and every request 401s. All variants are HMAC over the
# same shared secret, so accepting the wider set costs nothing security-wise (a forger
# still needs the secret) and makes the service tolerant of the issuer's algorithm.
# Union with the configured value so an env that pins JWT_ALGORITHM can't re-break this.
_ALLOWED_ALGORITHMS = sorted(
    {a.strip() for a in settings.JWT_ALGORITHM.split(",") if a.strip()}
    | {"HS256", "HS512"}
)


class CurrentUser:
    def __init__(
        self,
        user_id: str,
        email: str,
        user_name: str,
        org_id: str,
        role: str,
    ):
        self.user_id = user_id
        self.email = email
        self.user_name = user_name
        self.org_id = org_id
        self.role = role.upper()

    @property
    def is_manager(self) -> bool:
        return self.role in ("MANAGER", "ADMIN", "ORG_ADMIN")

    @property
    def is_employee(self) -> bool:
        return self.role == "EMPLOYEE"

    @property
    def is_admin(self) -> bool:
        return self.role in ("ADMIN", "ORG_ADMIN")


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=_ALLOWED_ALGORITHMS,
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    payload = _decode_token(credentials.credentials)

    user_id = payload.get("userId") or payload.get("sub", "")
    email = payload.get("sub", "")
    user_name = payload.get("name", email)
    org_id = payload.get("orgId", "")
    role = payload.get("role", "EMPLOYEE")

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing orgId claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=user_id,
        email=email,
        user_name=user_name,
        org_id=org_id,
        role=role,
    )


def require_manager(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin access required",
        )
    return current_user


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user