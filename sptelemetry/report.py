"""Markdown report generation."""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from .analysis import AnalysisConfig, AnalysisResult
from .diagnosis import infer_health
from .models import AnomalyEvent, TelemetryRow


def build_health_report(
    result: AnalysisResult,
    *,
    source: str = "stream",
    config: AnalysisConfig | None = None,
    rows: list[TelemetryRow] | None = None,
    time_span: tuple[datetime, datetime] | None = None,
    max_events: int = 12,
) -> str:
    config = config or AnalysisConfig()
    status, likely_mode, next_check = infer_health(result.events, result.summaries)
    lines = [
        "# Silicon Photonics Telemetry Health Report",
        "",
        f"- **Source:** {source}",
        f"- **Samples analyzed:** {result.rows_seen}",
        f"- **Overall status:** {status.upper()}",
    ]
    if rows:
        lines.append(f"- **Time span:** {_format_dt(rows[0].timestamp)} to {_format_dt(rows[-1].timestamp)}")
    elif time_span:
        lines.append(f"- **Time span:** {_format_dt(time_span[0])} to {_format_dt(time_span[1])}")
    lines.extend(
        [
            f"- **Likely failure mode:** {likely_mode}",
            f"- **Next validation check:** {next_check}",
            "",
            "## Event Summary",
            "",
        ]
    )

    if result.events:
        severity_counts = Counter(event.severity for event in result.events)
        metric_counts = Counter(event.metric for event in result.events)
        lines.append(
            f"{len(result.events)} anomaly/drift event(s): "
            + ", ".join(f"{severity}={count}" for severity, count in sorted(severity_counts.items()))
            + "."
        )
        lines.append("")
        lines.append("| metric | events |")
        lines.append("| --- | ---: |")
        for metric, count in metric_counts.most_common():
            lines.append(f"| {metric} | {count} |")
    else:
        lines.append("No guardrail, robust-z, EWMA, or sustained-change events were detected.")

    lines.extend(["", "## Top Events", ""])
    if result.events:
        lines.append("| timestamp | module | ch | metric | value | severity | why |")
        lines.append("| --- | --- | ---: | --- | ---: | --- | --- |")
        for event in result.events[:max_events]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _format_dt(event.timestamp),
                        event.module_id,
                        str(event.channel),
                        event.metric,
                        _format_value(event.metric, event.value),
                        event.severity,
                        event.reason,
                    ]
                )
                + " |"
            )
    else:
        lines.append("No events to list.")

    lines.extend(["", "## Metric Snapshot", ""])
    lines.append("| module | ch | metric | latest | min | max | mean | slope/sample | last robust z |")
    lines.append("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for summary in _prioritized_summaries(result):
        lines.append(
            "| "
            + " | ".join(
                [
                    summary.module_id,
                    str(summary.channel),
                    summary.metric,
                    _format_value(summary.metric, summary.latest),
                    _format_value(summary.metric, summary.minimum),
                    _format_value(summary.metric, summary.maximum),
                    _format_value(summary.metric, summary.mean),
                    f"{summary.slope_per_sample:.4g}",
                    f"{summary.last_robust_z:.2f}",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Methods",
            "",
            "- EWMA residuals compare each new sample with the previous exponentially weighted moving average.",
            "- Robust z-scores use the rolling median and MAD, so isolated spikes are visible without assuming Gaussian noise.",
            "- The change heuristic compares older and recent rolling medians in the bad direction for each metric.",
            f"- Parameters: alpha={config.ewma_alpha}, robust_window={config.robust_window}, "
            f"robust_z_threshold={config.robust_z_threshold}, change_window={config.change_window}.",
        ]
    )
    return "\n".join(lines) + "\n"


def _prioritized_summaries(result: AnalysisResult):
    event_metrics = {(event.module_id, event.channel, event.metric) for event in result.events}
    flagged = [s for s in result.summaries if (s.module_id, s.channel, s.metric) in event_metrics]
    if flagged:
        return sorted(flagged, key=lambda s: (s.module_id, s.channel, s.metric))
    return sorted(result.summaries, key=lambda s: (s.module_id, s.channel, s.metric))[:16]


def _format_dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _format_value(metric: str, value: float) -> str:
    if metric == "ber":
        return f"{value:.2e}"
    if metric == "voltage_v":
        return f"{value:.4f}"
    return f"{value:.3f}"
