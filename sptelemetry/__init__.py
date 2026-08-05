"""Silicon photonics telemetry monitor."""
from __future__ import annotations

from .analysis import AnalysisConfig, AnalysisResult, analyze_rows
from .data import FIELDNAMES, generate_csv, iter_csv
from .models import AnomalyEvent, MetricSummary, TelemetryRow
from .report import build_health_report

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "AnomalyEvent",
    "FIELDNAMES",
    "MetricSummary",
    "TelemetryRow",
    "analyze_rows",
    "build_health_report",
    "generate_csv",
    "iter_csv",
]
