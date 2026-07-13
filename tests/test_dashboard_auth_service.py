import re

import pytest

from stock_research.dashboard import auth_service
from stock_research.dashboard.auth_models import CurrentUser


def test_password_hash_round_trip_and_wrong_password_rejected():
    password_hash = auth_service.hash_password("secret-password")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert auth_service.verify_password("secret-password", password_hash) is True
    assert auth_service.verify_password("wrong-password", password_hash) is False


def test_generated_tokens_are_urlsafe_and_not_equal():
    first = auth_service.generate_token()
    second = auth_service.generate_token()

    assert first != second
    assert re.fullmatch(r"[A-Za-z0-9_-]+", first)


def test_current_user_read_model_uses_whitelisted_fields_only():
    user = CurrentUser(user_id="user:1", username="xiwei", display_name="Xiwei", role="admin", is_active=True)

    assert auth_service.current_user_read_model(user) == {
        "user_id": "user:1",
        "username": "xiwei",
        "display_name": "Xiwei",
        "role": "admin",
        "is_active": True,
    }


def test_csrf_validation_rejects_missing_or_mismatched_token():
    with pytest.raises(PermissionError, match="csrf_token_required"):
        auth_service.validate_csrf(csrf_cookie="", csrf_header="")

    with pytest.raises(PermissionError, match="csrf_token_mismatch"):
        auth_service.validate_csrf(csrf_cookie="abc", csrf_header="def")

    assert auth_service.validate_csrf(csrf_cookie="abc", csrf_header="abc") is None
