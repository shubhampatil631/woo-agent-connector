"""Tests for authentication strategies, header construction, and credential verification."""

import base64

import httpx
import pytest
import respx

from woo_connector.auth import (
    APIKeyAuth,
    OAuthAppAuth,
    get_auth_strategy,
    verify_credentials,
)
from woo_connector.config import AuthType, Settings


def test_api_key_auth_https_header():
    auth = APIKeyAuth(consumer_key="ck_test", consumer_secret="cs_test", is_https=True)
    req = httpx.Request("GET", "https://store.example.com/wp-json/wc/v3/orders")

    # Run generator
    generator = auth.auth_flow(req)
    authed_req = next(generator)

    expected_b64 = base64.b64encode(b"ck_test:cs_test").decode("ascii")
    assert authed_req.headers["Authorization"] == f"Basic {expected_b64}"
    assert "consumer_key" not in str(authed_req.url)


def test_api_key_auth_http_query_params(caplog):
    auth = APIKeyAuth(consumer_key="ck_test", consumer_secret="cs_test", is_https=False)
    req = httpx.Request("GET", "http://localhost:8080/wp-json/wc/v3/orders")

    generator = auth.auth_flow(req)
    authed_req = next(generator)

    assert "Authorization" not in authed_req.headers
    assert "consumer_key=ck_test" in str(authed_req.url)
    assert "consumer_secret=cs_test" in str(authed_req.url)


def test_oauth_app_auth_header():
    auth = OAuthAppAuth(consumer_key="ck_oauth_key", consumer_secret="cs_oauth_secret")
    req = httpx.Request("GET", "https://store.example.com/wp-json/wc/v3/products")

    generator = auth.auth_flow(req)
    authed_req = next(generator)

    expected_b64 = base64.b64encode(b"ck_oauth_key:cs_oauth_secret").decode("ascii")
    assert authed_req.headers["Authorization"] == f"Basic {expected_b64}"


def test_get_auth_strategy_factory():
    cfg_api = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_1",
        consumer_secret="cs_1",
        auth_type=AuthType.API_KEY,
    )
    strat_api = get_auth_strategy(cfg_api)
    assert isinstance(strat_api, APIKeyAuth)
    assert strat_api.is_https is True

    cfg_oauth = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_2",
        consumer_secret="cs_2",
        auth_type=AuthType.OAUTH,
    )
    strat_oauth = get_auth_strategy(cfg_oauth)
    assert isinstance(strat_oauth, OAuthAppAuth)


@respx.mock
async def test_verify_credentials_success():
    cfg = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_valid",
        consumer_secret="cs_valid",
    )
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=200,
        json={"environment": {"wp_version": "6.4"}},
    )

    result = await verify_credentials(cfg)
    assert result.success is True
    assert result.status_code == 200
    assert result.permissions == "read"


@respx.mock
async def test_verify_credentials_unauthorized():
    cfg = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_invalid",
        consumer_secret="cs_invalid",
    )
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=401,
        json={"code": "woocommerce_rest_cannot_view", "message": "Invalid credentials."},
    )

    result = await verify_credentials(cfg)
    assert result.success is False
    assert result.status_code == 401
    assert "Invalid Consumer Key or Secret" in result.message


@respx.mock
async def test_verify_credentials_forbidden():
    cfg = Settings(
        base_url="https://store.example.com",
        consumer_key="ck_forbidden",
        consumer_secret="cs_forbidden",
    )
    respx.get("https://store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=403,
        json={"code": "forbidden", "message": "Cannot view resources"},
    )

    result = await verify_credentials(cfg)
    assert result.success is False
    assert result.status_code == 403


async def test_verify_credentials_missing_keys():
    cfg = Settings(
        base_url="https://store.example.com",
        consumer_key="",
        consumer_secret="",
    )
    result = await verify_credentials(cfg)
    assert result.success is False
    assert result.status_code == 401
    assert "not configured" in result.message


@respx.mock
async def test_verify_credentials_connection_error():
    cfg = Settings(
        base_url="https://unreachable-store.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
    )
    respx.get("https://unreachable-store.example.com/wp-json/wc/v3/system_status").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await verify_credentials(cfg)
    assert result.success is False
    assert result.status_code == 503
    assert "Cannot connect" in result.message


@respx.mock
async def test_verify_credentials_timeout_and_unexpected():
    cfg = Settings(
        base_url="https://timeout-store.example.com",
        consumer_key="ck_test",
        consumer_secret="cs_test",
    )
    respx.get("https://timeout-store.example.com/wp-json/wc/v3/system_status").mock(
        side_effect=httpx.ReadTimeout("Timeout occurred")
    )

    result = await verify_credentials(cfg)
    assert result.success is False
    assert result.status_code == 504
    assert "timed out" in result.message

    respx.get("https://timeout-store.example.com/wp-json/wc/v3/system_status").respond(
        status_code=500,
        text="Internal server crash",
    )
    result_500 = await verify_credentials(cfg)
    assert result_500.success is False
    assert result_500.status_code == 500


def test_auth_cli_main(monkeypatch, capsys):
    from unittest.mock import AsyncMock, patch

    from woo_connector.auth import AuthVerificationResult, main

    mock_res = AuthVerificationResult(
        success=True,
        status_code=200,
        message="Authentication successful",
        permissions="read",
    )

    with patch("woo_connector.auth.verify_credentials", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = mock_res
        monkeypatch.setattr("sys.argv", ["auth", "--check"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "[OK]" in captured.out
