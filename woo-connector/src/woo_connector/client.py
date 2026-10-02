"""Async HTTP client for WooCommerce REST API."""

import httpx

from woo_connector.config import Settings, settings


class WooCommerceClient:
    """Async client for interacting with the WooCommerce REST API."""

    def __init__(self, config: Settings = settings):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "WooCommerceClient":
        self._client = httpx.AsyncClient(
            base_url=str(self.config.store_url).rstrip("/"),
            timeout=self.config.request_timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
