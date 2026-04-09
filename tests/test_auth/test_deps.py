import uuid

import pytest

from app.services.auth_service import create_access_token, create_refresh_token, decode_token


def test_access_token_contains_role() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "viewer")
    payload = decode_token(token)

    assert payload["role"] == "viewer"
    assert payload["type"] == "access"


def test_refresh_token_has_no_role() -> None:
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    payload = decode_token(token)

    assert "role" not in payload
    assert payload["type"] == "refresh"
