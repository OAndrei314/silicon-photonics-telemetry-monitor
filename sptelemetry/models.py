"""Typed records used by the telemetry monitor."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelemetryRow:
    timestamp: datetime
    module_id: str
    channel: int
    tx_power_dbm: float
    rx_power_dbm: float
    laser_bias_ma: float
    temperature_c: float
    tec_current_a: float
    voltage_v: float
    ber: float
    loss_db: float

    def metric_items(self) -> dict[str, float]:
        return {
            "tx_power_dbm": self.tx_power_dbm,
            "rx_power_dbm": self.rx_power_dbm,
            "laser_bias_ma": self.laser_bias_ma,
            "temperature_c": self.temperature_c,
            "tec_current_a": self.tec_current_a,
            "voltage_v": self.voltage_v,
            "ber": self.ber,
            "loss_db": self.loss_db,
        }


@dataclass(frozen=True)
class AnomalyEvent:
    timestamp: datetime
    module_id: str
    channel: int
    metric: str
    value: float
    severity: str
    reason: str
    score: float


@dataclass(frozen=True)
class MetricSummary:
    module_id: str
    channel: int
    metric: str
    count: int
    latest: float
    minimum: float
    maximum: float
    mean: float
    slope_per_sample: float
    last_robust_z: float
