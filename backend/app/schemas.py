"""Pydantic request payload models."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginPayload(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)


class SignupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=12, max_length=256)


class BaselineCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str
    week: str
    qty_cs: float = Field(ge=0, le=1_000_000_000)


class BaselineSave(BaseModel):
    market: str
    customer_id: int
    cells: list[BaselineCell] = Field(max_length=20_000)


class PromoPayload(BaseModel):
    id: int | None = None
    version: int | None = None
    market: str
    customer_id: int
    start_date: date
    end_date: date
    cons_start: date
    cons_end: date
    tactic: str
    items: dict[str, float] = Field(min_length=1, max_length=100)


class ListingPayload(BaseModel):
    market: str
    customer_id: int
    products: list[str] = Field(max_length=500)


class PipelineUpdate(BaseModel):
    enabled: bool
    schedule_frequency: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"]
    schedule_timezone: str = Field(min_length=1, max_length=100)
    schedule_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    schedule_weekday: int = Field(ge=0, le=6)
    schedule_month_day: int = Field(ge=1, le=31)
    schedule_quarter_month: int = Field(ge=1, le=3)
    schedule_start_date: date | None = None
    schedule_end_date: date | None = None
    file_path: str | None = Field(default=None, max_length=500)


class PipelineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    direction: Literal["INBOUND", "OUTBOUND"]
    source: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    connector_type: Literal[
        "FileConnector",
        "MockSapConnector",
        "MockP10Connector",
        "SapOdataConnector",
        "SftpConnector",
        "RestConnector",
    ]
    file_path: str | None = Field(default=None, max_length=500)
    enabled: bool = False
    schedule_frequency: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"] = "DAILY"
    schedule_timezone: str = "UTC"
    schedule_time: str = Field(default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    schedule_weekday: int = Field(default=1, ge=0, le=6)
    schedule_month_day: int = Field(default=1, ge=1, le=31)
    schedule_quarter_month: int = Field(default=1, ge=1, le=3)
    schedule_start_date: date | None = None
    schedule_end_date: date | None = None


class UserAccessAssignment(BaseModel):
    market_code: str
    customer_id: int


class AdminUserUpdate(BaseModel):
    role: Literal["PLANNER", "APPROVER", "ADMIN", "VIEWER"]
    active: bool
    assignments: list[UserAccessAssignment] = Field(max_length=500)
    sales_org_access: list[str] = Field(max_length=100, default_factory=list)
    admin_sales_org_access: list[str] = Field(max_length=100, default_factory=list)


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=2, max_length=100)
    role: Literal["PLANNER", "APPROVER", "VIEWER"]
    password: str = Field(min_length=12, max_length=256)
    active: bool = True
    sales_org_access: list[str] = Field(max_length=100, default_factory=list)
    assignments: list[UserAccessAssignment] = Field(max_length=500)
    admin_sales_org_access: list[str] = Field(max_length=100, default_factory=list)


class MasterFileUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=15_000_000)


class BaselineFileUpload(MasterFileUpload):
    market: str
    customer_id: int
