import argparse
import asyncio
import base64
import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from woo_connector.config import AuthType, Settings, settings

logger = logging.getLogger(__name__)

_HTTP_AUTH_WARNED = False


def _build_basic_auth_header(username: str, password: str) -> str:
    userpass = f"{username}:{password}".encode()
    return f"Basic {base64.b64encode(userpass).decode('ascii')}"


@dataclass(frozen=True)
class AuthVerificationResult:
    """Result of validating WooCommerce credentials."""

    success: bool
    status_code: int
    message: str
    permissions: str | None = None
    warning: str | None = None


class AuthStrategy(httpx.Auth, ABC):
    """Abstract base class for WooCommerce authentication strategies."""

    @abstractmethod
    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        """Apply authentication to outgoing httpx requests."""
        yield request


class APIKeyAuth(AuthStrategy):
    """API Key authentication strategy supporting HTTPS Basic Auth and HTTP Query Params."""

    def __init__(self, consumer_key: str, consumer_secret: str, is_https: bool = False):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.is_https = is_https

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        global _HTTP_AUTH_WARNED

        if self.is_https or str(request.url).startswith("https://"):
            request.headers["Authorization"] = _build_basic_auth_header(
                self.consumer_key, self.consumer_secret
            )
        else:
            if not _HTTP_AUTH_WARNED:
                logger.warning(
                    "Plain HTTP detected: Using query-parameter authentication. "
                    "This is for local development only and insecure for production."
                )
                _HTTP_AUTH_WARNED = True

            url_parts = urlsplit(str(request.url))
            query_params = dict(parse_qsl(url_parts.query))
            query_params["consumer_key"] = self.consumer_key
            query_params["consumer_secret"] = self.consumer_secret

            new_query = urlencode(query_params)
            new_url = urlunsplit((
                url_parts.scheme,
                url_parts.netloc,
                url_parts.path,
                new_query,
                url_parts.fragment,
            ))
            request.url = httpx.URL(new_url)

        yield request


class OAuthAppAuth(AuthStrategy):
    """OAuth/App-authorization authentication strategy."""

    def __init__(self, consumer_key: str, consumer_secret: str):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = _build_basic_auth_header(
            self.consumer_key, self.consumer_secret
        )
        yield request


def get_auth_strategy(config: Settings | None = None) -> AuthStrategy:
    """Factory creating the appropriate authentication strategy based on settings."""
    cfg = config or settings
    is_https = str(cfg.base_url).startswith("https://")

    if cfg.auth_type == AuthType.OAUTH:
        return OAuthAppAuth(cfg.consumer_key, cfg.consumer_secret)
    return APIKeyAuth(cfg.consumer_key, cfg.consumer_secret, is_https=is_https)


async def verify_credentials(
    config: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> AuthVerificationResult:
    """Verify WooCommerce API credentials against a lightweight endpoint."""
    cfg = config or settings
    auth = get_auth_strategy(cfg)
    base_url = str(cfg.base_url).rstrip("/")

    # Check for empty credentials
    if not cfg.consumer_key or not cfg.consumer_secret:
        return AuthVerificationResult(
            success=False,
            status_code=401,
            message="Consumer Key or Consumer Secret is not configured.",
        )

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=base_url,
        auth=auth,
        timeout=cfg.request_timeout,
    )

    try:
        # Use lightweight system_status or data endpoint
        response = await http_client.get("/wp-json/wc/v3/system_status")

        if response.status_code in (200, 201):
            perm_warning = None
            permissions = "read"

            content_type = response.headers.get("content-type", "")
            data = response.json() if content_type.startswith("application/json") else {}
            if isinstance(data, dict) and data.get("environment", {}).get("wp_version"):
                pass

            return AuthVerificationResult(
                success=True,
                status_code=response.status_code,
                message="WooCommerce REST API authentication successful.",
                permissions=permissions,
                warning=perm_warning,
            )

        if response.status_code == 401:
            return AuthVerificationResult(
                success=False,
                status_code=401,
                message="Authentication failed: Invalid Consumer Key or Secret.",
            )

        if response.status_code == 403:
            return AuthVerificationResult(
                success=False,
                status_code=403,
                message="Authorization failed: Key does not have sufficient permissions.",
            )

        return AuthVerificationResult(
            success=False,
            status_code=response.status_code,
            message=(
                f"WooCommerce API returned status {response.status_code}: "
                f"{response.text[:150]}"
            ),
        )

    except httpx.ConnectError as e:
        return AuthVerificationResult(
            success=False,
            status_code=503,
            message=f"Cannot connect to WooCommerce store at {base_url}: {e}",
        )
    except httpx.TimeoutException as e:
        return AuthVerificationResult(
            success=False,
            status_code=504,
            message=f"Connection to store timed out after {cfg.request_timeout}s: {e}",
        )
    except Exception as e:
        return AuthVerificationResult(
            success=False,
            status_code=500,
            message=f"Unexpected error validating credentials: {e}",
        )
    finally:
        if owns_client:
            await http_client.aclose()


def main() -> None:
    """CLI tool for verifying credentials with python -m woo_connector.auth --check."""
    parser = argparse.ArgumentParser(description="WooCommerce Authentication CLI")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check and verify configured WooCommerce API credentials",
    )
    args = parser.parse_args()

    if args.check or len(sys.argv) == 1:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        cfg = settings
        print(f"Checking credentials for {cfg.base_url} (auth_type={cfg.auth_type})...")
        result = asyncio.run(verify_credentials(cfg))

        if result.success:
            print(
                f"[OK] {result.message} "
                f"(HTTP {result.status_code}, permissions={result.permissions})"
            )
            if result.warning:
                print(f"[WARNING] {result.warning}")
            sys.exit(0)
        else:
            print(f"[FAIL] {result.message} (HTTP {result.status_code})")
            sys.exit(1)


if __name__ == "__main__":
    main()
