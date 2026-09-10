from copy import deepcopy

import sla_config
from sla_config import SlaConfigError


def _defaults():
    return deepcopy(sla_config.load_sla_config())


def test_defaults_load_from_yaml():
    cfg = sla_config.load_sla_config()
    assert cfg["severity_sla_hours"]["Critical"] == 2
    assert cfg["severity_sla_hours"]["Low"] == 72
    assert cfg["category_multipliers"]["Security"] == 0.5
    assert cfg["workload_bump_threshold"] == 3


def test_config_missing_keys_rejected():
    bad = _defaults()
    del bad["severity_sla_hours"]
    try:
        sla_config._validate(bad)
    except SlaConfigError as exc:
        assert "severity_sla_hours" in str(exc)
    else:
        raise AssertionError("expected SlaConfigError")


def test_effective_hours_and_risk_mapping():
    hours, risk, line = sla_config.compute_sla("Critical", "Security", 0)
    assert hours == 1.0  # 2h base x 0.5 multiplier
    assert risk == "High"  # <= 4h threshold
    assert "[SLA rule]" in line

    hours, risk, _ = sla_config.compute_sla("Low", "General", 0)
    assert hours == 108.0  # 72h x 1.5
    assert risk == "Low"


def test_workload_bumps_risk():
    _, risk_low, _ = sla_config.compute_sla("Medium", "General", 2)
    _, risk_bumped, _ = sla_config.compute_sla("Medium", "General", 3)
    assert risk_low == "Low"
    assert risk_bumped == "Medium"  # bumped one level at threshold 3


def test_request_specific_override_does_not_change_defaults():
    rules = _defaults()
    rules["severity_sla_hours"]["High"] = 2
    hours, risk, _ = sla_config.compute_sla("High", "Security", 0, rules)
    assert hours == 1.0 and risk == "High"
    default_hours, _, _ = sla_config.compute_sla("High", "Security", 0)
    assert default_hours == 4.0
