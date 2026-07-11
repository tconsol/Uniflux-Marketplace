import pytest
from fastapi import HTTPException
from app.middleware.auth_middleware import require_super_admin, CurrentUser


def _user(role):
    return CurrentUser(user_id="u", email="e@e.com", user_name="n", org_id="ORG_X", role=role)


def test_super_admin_allowed():
    u = _user("SUPER_ADMIN")
    assert require_super_admin(current_user=u) is u


def test_non_super_admin_forbidden():
    with pytest.raises(HTTPException) as exc:
        require_super_admin(current_user=_user("ORG_ADMIN"))
    assert exc.value.status_code == 403
