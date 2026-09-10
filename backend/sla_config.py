"""Load and evaluate SLA business rules.



Rules live in ``config/sla_rules.yaml``. They can be overridden at runtime
(per server session) through the admin API ``PUT /api/admin/sla-config``.
The active configuration is the YAML default unless a runtime override has
been applied; the override replaces the whole rule set so it is easy to
demonstrate "SLA rules are configurable".
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, Tuple

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "sla_rules.yaml")


_REQUIRED_KEYS = (
    "severity_sla_hours",
    "category_multipliers",
    "risk_thresholds_hours",
    "workload_bump_threshold",
)


class SlaConfigError(ValueError):
    """Raised when SLA rules are missing or malformed."""


def load_sla_config() -> Dict[str, Any]:
    """Load the default rule set from the YAML file on disk."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError as exc:
        raise SlaConfigError(
            f"Cannot read SLA config at {_CONFIG_PATH}: {exc}"
        ) from exc
    _validate(data)
    return data


def _validate(rules: Dict[str, Any]) -> None:
    if not isinstance(rules, dict):
        raise SlaConfigError("SLA config must be a YAML mapping.")

    missing = [key for key in _REQUIRED_KEYS if key not in rules]
    if missing:
        raise SlaConfigError(
            f"SLA config is missing required keys: {', '.join(missing)}"
        )
    from models import CATEGORIES, SEVERITIES

    for group, keys in {
        "severity_sla_hours": SEVERITIES,
        "category_multipliers": CATEGORIES,
        "risk_thresholds_hours": ("high", "medium"),
    }.items():
        if not isinstance(rules[group], dict):
            raise SlaConfigError(f"Invalid {group}")

        for key in keys:
            value = rules[group].get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise SlaConfigError(f"{group}.{key} must be a positive finite number")

    threshold = rules["workload_bump_threshold"]
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
        raise SlaConfigError("workload_bump_threshold must be a non-negative integer")

    if (
        rules["risk_thresholds_hours"]["high"]
        > rules["risk_thresholds_hours"]["medium"]
    ):
        raise SlaConfigError(
            "High-risk threshold must not exceed medium-risk threshold"
        )


def compute_sla(
    severity: str,
    category: str,
    team_open_tickets: int,
    rules: Dict[str, Any] | None = None,
) -> Tuple[float, str, str]:
    """Compute the effective resolution target and a workload-aware risk level.



    Returns ``(effective_hours, risk_level, explanation_line)`` where
    ``risk_level`` is one of ``"Low"``, ``"Medium"``, ``"High"``.
    """
    cfg = rules if rules is not None else load_sla_config()
    base_hours = float(cfg["severity_sla_hours"].get(severity, 24.0))
    multiplier = float(cfg["category_multipliers"].get(category, 1.0))
    effective_hours = base_hours * multiplier
    high_max = float(cfg["risk_thresholds_hours"].get("high", 4.0))
    medium_max = float(cfg["risk_thresholds_hours"].get("medium", 12.0))
    if effective_hours <= high_max:
        risk = "High"
    elif effective_hours <= medium_max:
        risk = "Medium"
    else:
        risk = "Low"
    bump_at = int(cfg["workload_bump_threshold"])
    if team_open_tickets >= bump_at and risk != "High":
        risk = "High" if risk == "Medium" else "Medium"
    line = (
        f"\n[SLA rule] predicted_resolution_target={effective_hours:.1f}h "
        f"(severity {severity} base {base_hours:g}h x category {category} "
        f"multiplier {multiplier:g}), team_open={team_open_tickets}, "
        f"breach_risk={risk}"
    )
    return effective_hours, risk, line
