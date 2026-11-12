from api.keycloak_auth import principal_email, token_is_for_client


def test_token_accepts_keycloak_account_audience() -> None:
    assert token_is_for_client({"aud": "account", "azp": "job-platform"}, "job-platform")
    assert token_is_for_client({"aud": "account"}, "job-platform")
    assert token_is_for_client({"aud": ["account"]}, "job-platform")
    assert token_is_for_client({"azp": "job-platform"}, "job-platform")
    assert token_is_for_client({"aud": "job-platform"}, "job-platform")


def test_token_rejects_other_clients() -> None:
    assert not token_is_for_client({"azp": "other-app", "aud": "account"}, "job-platform")


def test_principal_email_fallbacks() -> None:
    assert principal_email({"email": "Jake@Example.com"}) == "jake@example.com"
    assert principal_email({"preferred_username": "jake@example.com"}) == "jake@example.com"
    assert principal_email({"preferred_username": "jake"}) == "jake@homelab.local"
    assert principal_email({"sub": "abc-123"}) == "abc-123@homelab.local"
    assert principal_email({}) is None
