from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessError(Exception):
    def __init__(self, code: str, message: str = "", retryable: bool = False):
        super().__init__(code)
        self.code, self.message, self.retryable = code, message or code, retryable


def utc_now():
    return datetime.now(UTC)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["cancel", "return", "exchange"]
    order_id: str
    line_id: str | None = None
    quantity: int = Field(default=1, ge=1, le=100)
    target_variant: str | None = None
    reason: str = Field(default="用户申请", max_length=500)
