"""Legal policy acceptance schemas."""
from datetime import datetime

from pydantic import BaseModel


class PolicyAcceptanceOut(BaseModel):
    accepted: bool
    policies_version: str
    policies_accepted_at: datetime
    next_url: str
    message: str