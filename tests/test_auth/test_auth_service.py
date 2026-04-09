import uuid

import pytest

from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password() -> None:
    password = "test_password_123"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_create_access_token() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "admin")

    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_create_refresh_token() -> None:
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)

    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "refresh"


def test_decode_invalid_token() -> None:
    from jose import JWTError

    with pytest.raises(JWTError):
        decode_token("invalid.token.here")
