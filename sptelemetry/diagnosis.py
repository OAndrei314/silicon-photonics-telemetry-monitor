"""Rule-based diagnosis for optical-module telemetry symptoms."""
from __future__ import annotations

from collections import Counter, defaultdict

from .models import AnomalyEvent, MetricSummary


def infer_health(events: list[AnomalyEvent], summaries: list[MetricSummary]) -> tuple[str, str, str]:
    """Return `(status, likely_failure_mode, next_validation_check)`."""
    severity = _overall_status(events)
    metrics = Counter(event.metric for event in events)
    reasons = " ".join(event.reason.lower() for event in events[:40])

    if metrics["temperature_c"] >= 3 and metrics["tec_current_a"] >= 3:
        return (
            severity,
            "Thermal-control saturation or degraded heat sinking is likely.",
            "Check heatsink contact, airflow, inlet temperature, and TEC setpoint tracking under a known workload.",
        )

    if metrics["voltage_v"] >= 3 and ("below" in reasons or "above" in reasons):
        return (
            severity,
            "Power-rail instability may be disturbing the optical front end.",
            "Scope the module supply at the cage during load changes and compare ripple and droop against the rail spec.",
        )

    if (
        metrics["rx_power_dbm"] >= 3
        and metrics["loss_db"] >= 3
        and metrics["tx_power_dbm"] <= max(1, metrics["rx_power_dbm"] // 3)
    ):
        return (
            severity,
            "Connector, fiber, or receive-coupling contamination is the leading suspect.",
            "Clean and inspect fiber endfaces, then compare receive power against an optical power meter and short loopback.",
        )

    if metrics["laser_bias_ma"] >= 3 and (
        metrics["tx_power_dbm"] >= 2 or _has_positive_slope(summaries, "laser_bias_ma", 0.06)
    ):
        return (
            severity,
            "Laser aging or bias-control headroom exhaustion is likely.",
            "Run an L-I sweep and optical spectrum check, then compare required bias current against module acceptance data.",
        )

    if metrics["ber"] >= 3 and (metrics["rx_power_dbm"] >= 2 or metrics["tx_power_dbm"] >= 2):
        return (
            severity,
            "Optical signal-margin loss is causing elevated BER.",
            "Run PRBS/BERT at target line rate while logging optical power, eye margin, and module alarms.",
        )

    if events:
        return (
            severity,
            "Slow parametric drift is visible but the failure mode is not uniquely isolated.",
            "Repeat the run with a longer baseline and validate the highest-scoring metric with bench instrumentation.",
        )

    return (
        "nominal",
        "No actionable failure signature detected.",
        "Keep collecting baseline telemetry and rerun analysis after the next thermal or traffic stress interval.",
    )


def maintenance_priority(events: list[AnomalyEvent], limit: int = 5) -> list[dict[str, object]]:
    """Rank module/channel pairs by operational urgency."""
    scores: dict[tuple[str, int], float] = defaultdict(float)
    metrics: dict[tuple[str, int], Counter[str]] = defaultdict(Counter)
    latest_reason: dict[tuple[str, int], str] = {}
    for event in events:
        key = (event.module_id, event.channel)
        scores[key] += _event_weight(event)
        metrics[key][event.metric] += 1
        latest_reason[key] = event.reason
    rows = []
    for (module_id, channel), score in scores.items():
        primary_metric, _count = metrics[(module_id, channel)].most_common(1)[0]
        rows.append(
            {
                "module_id": module_id,
                "channel": channel,
                "priority_score": round(score, 3),
                "primary_metric": primary_metric,
                "event_count": sum(metrics[(module_id, channel)].values()),
                "recommended_action": _action_for_metrics(metrics[(module_id, channel)]),
                "latest_reason": latest_reason[(module_id, channel)],
            }
        )
    rows.sort(key=lambda row: (-float(row["priority_score"]), str(row["module_id"]), int(row["channel"])))
    return rows[:limit]


def _overall_status(events: list[AnomalyEvent]) -> str:
    severities = {event.severity for event in events}
    if "critical" in severities:
        return "critical"
    if "degraded" in severities:
        return "degraded"
    if "watch" in severities:
        return "watch"
    return "nominal"


def _has_positive_slope(summaries: list[MetricSummary], metric: str, threshold: float) -> bool:
    return any(summary.metric == metric and summary.slope_per_sample >= threshold for summary in summaries)


def _event_weight(event: AnomalyEvent) -> float:
    severity = {"watch": 1.0, "degraded": 2.5, "critical": 5.0}.get(event.severity, 0.5)
    return severity + min(5.0, event.score)


def _action_for_metric(metric: str) -> str:
    actions = {
        "rx_power_dbm": "inspect fiber path and receive coupling",
        "loss_db": "clean connector and rerun optical loss measurement",
        "laser_bias_ma": "run L-I sweep and check bias headroom",
        "temperature_c": "check heatsink contact and airflow",
        "tec_current_a": "verify TEC setpoint tracking under load",
        "voltage_v": "scope module power rail during traffic bursts",
        "ber": "run PRBS/BERT with power and eye-margin logging",
        "tx_power_dbm": "verify transmit optical power calibration",
    }
    return actions.get(metric, "repeat validation with a longer baseline")


def _action_for_metrics(metrics: Counter[str]) -> str:
    if metrics["ber"] and (metrics["rx_power_dbm"] or metrics["loss_db"]):
        return "inspect fiber path and connector cleanliness, then run PRBS/BERT with eye-margin logging"
    if metrics["temperature_c"] and metrics["tec_current_a"]:
        return "check thermal path, heatsink contact, airflow and TEC setpoint tracking"
    primary, _count = metrics.most_common(1)[0]
    return _action_for_metric(primary)
