"""Pydantic v2 domain and response models for Orders, Inventory, and Store Status."""

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with common pydantic configuration."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )


T = TypeVar("T", bound=BaseSchema)


class OrderStatus(StrEnum):
    """Supported WooCommerce order statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    ON_HOLD = "on-hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"
    ANY = "any"


class StockStatus(StrEnum):
    """Supported WooCommerce stock statuses."""

    IN_STOCK = "instock"
    OUT_OF_STOCK = "outofstock"
    ON_BACKORDER = "onbackorder"


class LineItem(BaseSchema):
    """Individual purchased item in an order."""

    product_id: int
    variation_id: int | None = None
    name: str
    sku: str | None = None
    quantity: int
    total: str


class Address(BaseSchema):
    """Customer billing or shipping address with PII redaction applied."""

    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    company: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None


class RefundItem(BaseSchema):
    """Summary of an order refund."""

    id: int
    reason: str | None = None
    total: str


class OrderSummary(BaseSchema):
    """Compact representation of an order for agent listing and searching."""

    id: int
    number: str
    status: str
    date_created: str
    total: str
    currency: str
    item_count: int
    customer_ref: str
    payment_method: str


class OrderDetail(BaseSchema):
    """Comprehensive details of an order including line items and redacted addresses."""

    id: int
    number: str
    status: str
    date_created: str
    total: str
    currency: str
    item_count: int
    customer_ref: str
    payment_method: str
    line_items: list[LineItem] = Field(default_factory=list)
    shipping_total: str = "0.00"
    discount_total: str = "0.00"
    refunds: list[RefundItem] = Field(default_factory=list)
    notes_available: bool = False
    billing: Address = Field(default_factory=Address)
    shipping: Address = Field(default_factory=Address)

    @property
    def summary(self) -> OrderSummary:
        """Derive an OrderSummary from the detailed order."""
        return OrderSummary(
            id=self.id,
            number=self.number,
            status=self.status,
            date_created=self.date_created,
            total=self.total,
            currency=self.currency,
            item_count=self.item_count,
            customer_ref=self.customer_ref,
            payment_method=self.payment_method,
        )


class ProductSummary(BaseSchema):
    """Compact representation of a product or variation in the store catalog."""

    id: int
    name: str
    sku: str | None = None
    type: str = "simple"
    status: str = "publish"
    price: str = "0.00"
    stock_status: str = "instock"
    stock_quantity: int | None = None
    manage_stock: bool = False


class StockInfo(BaseSchema):
    """Targeted inventory and stock level information for a product or SKU."""

    product_id: int
    sku: str | None = None
    stock_status: str
    stock_quantity: int | None = None
    low_stock: bool = False
    backorders: str | bool = False


class StoreStatus(BaseSchema):
    """Health, connectivity, and configuration metadata for the connected store."""

    connected: bool
    store_url: str
    wp_version: str | None = None
    wc_version: str | None = None
    currency: str | None = None
    currency_symbol: str | None = None
    timezone: str | None = None


class PaginatedResult(BaseSchema, Generic[T]):
    """Generic paginated wrapper for lists of domain resources."""

    items: list[T]
    page: int
    per_page: int
    total: int | None = None
    total_pages: int | None = None
    has_more: bool = False


class ToolError(BaseSchema):
    """Structured, actionable error returned to LLM agent."""

    code: str
    message: str
    retryable: bool = False
    retry_after: float | None = None
