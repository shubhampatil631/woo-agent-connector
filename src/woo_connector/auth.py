"""Authentication handlers for WooCommerce REST API (API Key and OAuth 1.0a)."""

import httpx


class WooCommerceAuth(httpx.Auth):
    """Base authentication handler for WooCommerce requests."""

    def __init__(self, consumer_key: str, consumer_secret: str):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

    def auth_flow(self, request: httpx.Request):
        # Basic auth implementation for HTTPS / API Key authentication
        request.headers["Authorization"] = httpx.BasicAuth(
            self.consumer_key, self.consumer_secret
        )._build_auth_header()
        yield request
