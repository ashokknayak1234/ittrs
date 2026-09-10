"""Validated request, response, and model-output contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = (
    "Hardware",
    "Software",
    "Network",
    "Access",
    "Security",
    "Billing",
    "General",
)
SEVERITIES = ("Low", "Medium", "High", "Critical")
TEAMS = ("Team Alpha", "Team Beta", "Team Gamma", "On-Call Team")


class TriageRequest(BaseModel):
    complaint_text: str = Field(min_length=1, max_length=10000)


class SecurityFlags(BaseModel):
    pii_redacted: bool


class Ticket(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    category: str
    severity: str
    team: str
    sla_risk_level: str
    decision_rationale: str
    escalation_status: str


class TriageResponse(BaseModel):
    status: str
    security_flags: SecurityFlags
    ticket: Ticket


class OverrideRequest(BaseModel):
    team: str = Field(min_length=1, max_length=100)
    severity: str = Field(min_length=1, max_length=30)
    override_reason: str = Field(min_length=1, max_length=2000)


class OverrideResponse(BaseModel):
    status: str
    ticket: Ticket


class NotSatisfiedRequest(BaseModel):
    comment: str = Field(default="", max_length=2000)


class NotSatisfiedResponse(OverrideResponse):
    sla_alerted: bool


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


class AdminDashboardResponse(BaseModel):
    workload: dict[str, int]
    total_tickets: int
    critical_tickets: int
    sla_alerts: int
    not_satisfied: int
    tickets: list[Ticket]


class SlaConfig(BaseModel):
    severity_sla_hours: dict[str, float]
    category_multipliers: dict[str, float]
    risk_thresholds_hours: dict[str, float]
    workload_bump_threshold: int = Field(ge=0)


class SlaConfigResponse(BaseModel):
    source: str
    config: SlaConfig


class TicketDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Literal[
        "Hardware", "Software", "Network", "Access", "Security", "Billing", "General"
    ]
    severity: Literal["Low", "Medium", "High", "Critical"]
    team: Literal["Team Alpha", "Team Beta", "Team Gamma", "On-Call Team"]
    decision_rationale: str = Field(min_length=1, max_length=4000)
