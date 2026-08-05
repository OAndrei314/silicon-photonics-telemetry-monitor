"""Streaming anomaly and drift analysis."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .models import AnomalyEvent, MetricSummary, TelemetryRow

METRICS = [
    "tx_power_dbm",
    "rx_power_dbm",
    "laser_bias_ma",
    "temperature_c",
    "tec_current_a",
    "voltage_v",
    "ber",
    "loss_db",
]

HIGH_IS_BAD = {"laser_bias_ma", "temperature_c", "tec_current_a", "ber", "loss_db"}
LOW_IS_BAD = {"tx_power_dbm", "rx_power_dbm"}
TWO_SIDED = {"voltage_v"}

MIN_EVENT_DELTA = {
    "tx_power_dbm": 0.35,
    "rx_power_dbm": 0.45,
    "laser_bias_ma": 3.0,
    "temperature_c": 3.0,
    "tec_current_a": 0.16,
    "voltage_v": 0.055,
    "ber": 5e-10,
    "loss_db": 0.45,
}

MIN_SCALE = {
    "tx_power_dbm": 0.08,
    "rx_power_dbm": 0.10,
    "laser_bias_ma": 0.8,
    "temperature_c": 0.5,
    "tec_current_a": 0.04,
    "voltage_v": 0.018,
    "ber": 1e-10,
    "loss_db": 0.08,
}

GUARDRAILS = {
    "tx_power_dbm": {"watch_low": -1.6, "critical_low": -2.4},
    "rx_power_dbm": {"watch_low": -5.5, "critical_low": -7.5},
    "laser_bias_ma": {"watch_high": 62.0, "critical_high": 78.0},
    "temperature_c": {"watch_high": 70.0, "critical_high": 82.0},
    "tec_current_a": {"watch_high": 1.15, "critical_high": 1.65},
    "voltage_v": {"watch_low": 3.18, "critical_low": 3.10, "watch_high": 3.42, "critical_high": 3.50},
    "ber": {"watch_high": 1e-9, "critical_high": 1e-6},
    "loss_db": {"watch_high": 4.2, "critical_high": 6.0},
}


@dataclass(frozen=True)
class AnalysisConfig:
    ewma_alpha: float = 0.2
    robust_window: int = 32
    robust_z_threshold: float = 4.0
    change_window: int = 8
    change_z_threshold: float = 2.5


@dataclass(frozen=True)
class AnalysisResult:
    rows_seen: int
    summaries: list[MetricSummary]
    events: list[AnomalyEvent]


@dataclass
class _MetricState:
    values: deque[float]
    ewma: float | None = None
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    latest: float | None = None
    first: float | None = None
    last_robust_z: float = 0.0


def analyze_rows(
    rows: Iterable[TelemetryRow],
    config: AnalysisConfig | None = None,
) -> AnalysisResult:
    """Analyze telemetry as a stream and return summaries plus noteworthy events."""
    config = config or AnalysisConfig()
    states: dict[tuple[str, int, str], _MetricState] = {}
    events: list[AnomalyEvent] = []
    rows_seen = 0

    for row in rows:
        rows_seen += 1
        for metric, value in row.metric_items().items():
            key = (row.module_id, row.channel, metric)
            state = states.setdefault(key, _MetricState(values=deque(maxlen=config.robust_window)))
            robust_z = _robust_z(metric, value, state.values)
            ewma_score = _ewma_score(metric, value, state)
            reasons = _guardrail_reasons(metric, value)
            change_score = _change_score(metric, value, state.values, config)

            if _bad_direction(metric, robust_z) and abs(robust_z) >= config.robust_z_threshold:
                reasons.append(f"robust z {robust_z:.1f} versus rolling median/MAD")
            if ewma_score >= config.change_z_threshold and state.count >= max(4, config.change_window // 2):
                reasons.append(f"EWMA residual {ewma_score:.1f}x rolling scale")
            if change_score >= config.change_z_threshold:
                reasons.append(f"sustained change {change_score:.1f}x rolling scale")

            if reasons:
                severity = _severity(metric, value, robust_z, ewma_score, change_score)
                events.append(
                    AnomalyEvent(
                        timestamp=row.timestamp,
                        module_id=row.module_id,
                        channel=row.channel,
                        metric=metric,
                        value=value,
                        severity=severity,
                        reason="; ".join(reasons),
                        score=round(max(abs(robust_z), ewma_score, change_score), 3),
                    )
                )

            _update_state(state, value, robust_z, config.ewma_alpha)

    summaries = _summaries(states)
    events.sort(key=lambda event: (_severity_rank(event.severity), event.score), reverse=True)
    return AnalysisResult(rows_seen=rows_seen, summaries=summaries, events=events)


def _robust_z(metric: str, value: float, prior_values: deque[float]) -> float:
    if len(prior_values) < 6:
        return 0.0
    center = median(prior_values)
    delta = value - center
    if _directional_delta(metric, value, center) < MIN_EVENT_DELTA[metric]:
        return 0.0
    scale = _robust_scale(metric, prior_values)
    if scale == 0:
        return 0.0 if value == center else 10.0
    return delta / scale


def _ewma_score(metric: str, value: float, state: _MetricState) -> float:
    if state.ewma is None or len(state.values) < 6:
        return 0.0
    if _directional_delta(metric, value, state.ewma) < MIN_EVENT_DELTA[metric]:
        return 0.0
    scale = _robust_scale(metric, state.values)
    if scale == 0:
        return 0.0
    return _directional_delta(metric, value, state.ewma) / scale


def _change_score(
    metric: str,
    value: float,
    prior_values: deque[float],
    config: AnalysisConfig,
) -> float:
    if len(prior_values) < config.change_window:
        return 0.0
    old = list(prior_values)[: config.change_window // 2]
    recent = list(prior_values)[-(config.change_window // 2) :]
    old_center = median(old)
    recent_center = median(recent)
    scale = _robust_scale(metric, prior_values)
    if scale == 0:
        return 0.0
    directional_change = _directional_delta(metric, recent_center, old_center)
    continuing = _directional_delta(metric, value, recent_center)
    if directional_change < MIN_EVENT_DELTA[metric] or continuing < -scale:
        return 0.0
    return directional_change / scale


def _bad_direction(metric: str, signed_score: float) -> bool:
    if metric in HIGH_IS_BAD:
        return signed_score > 0
    if metric in LOW_IS_BAD:
        return signed_score < 0
    return abs(signed_score) > 0


def _directional_delta(metric: str, new_value: float, old_value: float) -> float:
    if metric in HIGH_IS_BAD:
        return new_value - old_value
    if metric in LOW_IS_BAD:
        return old_value - new_value
    return abs(new_value - old_value)


def _robust_scale(metric: str, values: deque[float]) -> float:
    center = median(values)
    mad = median([abs(v - center) for v in values])
    if mad > 0:
        return max(1.4826 * mad, MIN_SCALE[metric])
    spread = max(values) - min(values)
    if spread:
        return max(spread / 2, MIN_SCALE[metric])
    return MIN_SCALE[metric]


def _guardrail_reasons(metric: str, value: float) -> list[str]:
    rules = GUARDRAILS[metric]
    reasons = []
    if "critical_low" in rules and value <= rules["critical_low"]:
        reasons.append(f"below critical floor {rules['critical_low']}")
    elif "watch_low" in rules and value <= rules["watch_low"]:
        reasons.append(f"below watch floor {rules['watch_low']}")

    if "critical_high" in rules and value >= rules["critical_high"]:
        reasons.append(f"above critical ceiling {rules['critical_high']}")
    elif "watch_high" in rules and value >= rules["watch_high"]:
        reasons.append(f"above watch ceiling {rules['watch_high']}")
    return reasons


def _severity(metric: str, value: float, robust_z: float, ewma_score: float, change_score: float) -> str:
    rules = GUARDRAILS[metric]
    if (
        ("critical_low" in rules and value <= rules["critical_low"])
        or ("critical_high" in rules and value >= rules["critical_high"])
        or abs(robust_z) >= 8
    ):
        return "critical"
    if abs(robust_z) >= 5.5 or ewma_score >= 4 or change_score >= 4:
        return "degraded"
    return "watch"


def _update_state(state: _MetricState, value: float, robust_z: float, ewma_alpha: float) -> None:
    state.count += 1
    state.total += value
    state.minimum = value if state.minimum is None else min(state.minimum, value)
    state.maximum = value if state.maximum is None else max(state.maximum, value)
    state.latest = value
    state.first = value if state.first is None else state.first
    state.last_robust_z = robust_z
    state.ewma = value if state.ewma is None else ewma_alpha * value + (1 - ewma_alpha) * state.ewma
    state.values.append(value)


def _summaries(states: dict[tuple[str, int, str], _MetricState]) -> list[MetricSummary]:
    summaries = []
    for (module_id, channel, metric), state in sorted(states.items()):
        if state.count == 0 or state.latest is None or state.first is None:
            continue
        summaries.append(
            MetricSummary(
                module_id=module_id,
                channel=channel,
                metric=metric,
                count=state.count,
                latest=state.latest,
                minimum=state.minimum if state.minimum is not None else state.latest,
                maximum=state.maximum if state.maximum is not None else state.latest,
                mean=state.total / state.count,
                slope_per_sample=(state.latest - state.first) / max(state.count - 1, 1),
                last_robust_z=state.last_robust_z,
            )
        )
    return summaries


def count_events_by_metric(events: Iterable[AnomalyEvent]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        counts[event.metric] += 1
    return dict(counts)


def _severity_rank(severity: str) -> int:
    return {"watch": 1, "degraded": 2, "critical": 3}.get(severity, 0)
