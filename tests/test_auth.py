from app.security.auth import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("s3cret!")
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    token = create_token("usr_x", "analyst", "analyst")
    payload = decode_token(token)
    assert payload["sub"] == "usr_x"
    assert payload["role"] == "analyst"