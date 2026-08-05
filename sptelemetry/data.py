"""CSV loading and deterministic telemetry generation."""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .models import TelemetryRow

FIELDNAMES = [
    "timestamp",
    "module_id",
    "channel",
    "tx_power_dbm",
    "rx_power_dbm",
    "laser_bias_ma",
    "temperature_c",
    "tec_current_a",
    "voltage_v",
    "ber",
    "loss_db",
]


def iter_csv(path: str | Path) -> Iterator[TelemetryRow]:
    """Yield telemetry rows from a CSV file without loading the full file."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = sorted(set(FIELDNAMES) - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"missing required CSV columns: {', '.join(missing)}")
        for raw in reader:
            yield TelemetryRow(
                timestamp=_parse_timestamp(raw["timestamp"]),
                module_id=raw["module_id"],
                channel=int(raw["channel"]),
                tx_power_dbm=float(raw["tx_power_dbm"]),
                rx_power_dbm=float(raw["rx_power_dbm"]),
                laser_bias_ma=float(raw["laser_bias_ma"]),
                temperature_c=float(raw["temperature_c"]),
                tec_current_a=float(raw["tec_current_a"]),
                voltage_v=float(raw["voltage_v"]),
                ber=float(raw["ber"]),
                loss_db=float(raw["loss_db"]),
            )


def write_csv(rows: Iterable[TelemetryRow], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_to_csv(row))


def generate_csv(
    path: str | Path,
    *,
    samples: int = 240,
    modules: int = 1,
    channels: int = 4,
    interval_seconds: int = 30,
    scenario: str = "nominal",
    seed: int = 7,
    start: datetime | None = None,
) -> None:
    """Generate deterministic silicon-photonics-style telemetry into `path`."""
    rows = generate_rows(
        samples=samples,
        modules=modules,
        channels=channels,
        interval_seconds=interval_seconds,
        scenario=scenario,
        seed=seed,
        start=start,
    )
    write_csv(rows, path)


def generate_rows(
    *,
    samples: int = 240,
    modules: int = 1,
    channels: int = 4,
    interval_seconds: int = 30,
    scenario: str = "nominal",
    seed: int = 7,
    start: datetime | None = None,
) -> list[TelemetryRow]:
    if samples <= 0:
        raise ValueError("samples must be positive")
    if modules <= 0:
        raise ValueError("modules must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    scenario = scenario.lower().replace("-", "_")
    valid = {"nominal", "fiber_contamination", "laser_aging", "thermal_runaway", "power_rail"}
    if scenario not in valid:
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {', '.join(sorted(valid))}")

    rng = random.Random(seed)
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[TelemetryRow] = []

    for sample_index in range(samples):
        timestamp = start + timedelta(seconds=sample_index * interval_seconds)
        progress = sample_index / max(samples - 1, 1)
        circadian = math.sin(sample_index / 24.0) * 0.08
        for module_index in range(modules):
            module_id = f"mod-{module_index + 1:02d}"
            module_offset = module_index * 0.03
            for channel in range(1, channels + 1):
                channel_offset = (channel - 1) * 0.05
                tx = -0.25 + channel_offset + rng.gauss(0, 0.035)
                insertion_loss = 2.15 + module_offset + channel_offset * 0.4 + rng.gauss(0, 0.045)
                bias = 42.0 + channel_offset * 2.0 + rng.gauss(0, 0.35)
                temp = 43.0 + module_offset * 7.0 + circadian + rng.gauss(0, 0.12)
                tec = 0.36 + module_offset + rng.gauss(0, 0.015)
                voltage = 3.30 + rng.gauss(0, 0.006)
                ber = max(1e-15, 3e-13 * (1 + rng.random() * 0.5))

                if scenario == "fiber_contamination" and channel == 2:
                    extra_loss = max(0.0, (progress - 0.28) / 0.72) * 4.8
                    insertion_loss += extra_loss
                    ber *= 1 + extra_loss * 9000

                if scenario == "laser_aging" and channel == 1:
                    bias += max(0.0, progress - 0.2) * 38
                    tx -= max(0.0, progress - 0.45) * 1.35
                    ber *= 1 + max(0.0, progress - 0.55) * 6000

                if scenario == "thermal_runaway":
                    heat = max(0.0, progress - 0.35) * 46
                    temp += heat
                    tec += heat / 34
                    bias += heat / 5
                    ber *= 1 + heat * 500

                if scenario == "power_rail" and sample_index > samples * 0.55:
                    sag = 0.11 + 0.03 * math.sin(sample_index)
                    voltage -= sag
                    tx -= sag * 2.6
                    ber *= 1 + sag * 40000

                rx = tx - insertion_loss + rng.gauss(0, 0.03)
                rows.append(
                    TelemetryRow(
                        timestamp=timestamp,
                        module_id=module_id,
                        channel=channel,
                        tx_power_dbm=round(tx, 4),
                        rx_power_dbm=round(rx, 4),
                        laser_bias_ma=round(bias, 4),
                        temperature_c=round(temp, 4),
                        tec_current_a=round(tec, 4),
                        voltage_v=round(voltage, 5),
                        ber=float(f"{ber:.4e}"),
                        loss_db=round(insertion_loss, 4),
                    )
                )
    return rows


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _row_to_csv(row: TelemetryRow) -> dict[str, str | int | float]:
    timestamp = row.timestamp.isoformat()
    if timestamp.endswith("+00:00"):
        timestamp = timestamp[:-6] + "Z"
    return {
        "timestamp": timestamp,
        "module_id": row.module_id,
        "channel": row.channel,
        "tx_power_dbm": row.tx_power_dbm,
        "rx_power_dbm": row.rx_power_dbm,
        "laser_bias_ma": row.laser_bias_ma,
        "temperature_c": row.temperature_c,
        "tec_current_a": row.tec_current_a,
        "voltage_v": row.voltage_v,
        "ber": row.ber,
        "loss_db": row.loss_db,
    }
