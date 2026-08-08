"""Rule-based diagnosis for optical-module telemetry symptoms."""
from __future__ import annotations

from collections import Counter

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
