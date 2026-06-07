"""Billing API schemas."""
from pydantic import BaseModel, Field


class CheckoutIn(BaseModel):
    amount_usd: int = Field(ge=10, le=500, description="Top-up amount in USD")