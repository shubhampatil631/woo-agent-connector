"""Pydantic v2 domain and response models for Orders and Inventory."""

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
