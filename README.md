# silicon-photonics-telemetry-monitor

Maintained by: codex-daily-routine

A dependency-light streaming telemetry analysis MVP for silicon-photonics-style optical
modules. It can generate or load CSV telemetry, flag anomalies and drift with transparent
heuristics, and produce a markdown health report with a likely failure mode and the next
bench validation check.

The goal is not to replace vendor diagnostics. It is a small, auditable first pass for
burn-in logs and lab notebooks where every threshold and decision rule should be
inspectable.

## Why this exists

Optical-module telemetry often arrives as CSV snapshots from firmware, CMIS tooling, bench
scripts, or manufacturing logs. This tool keeps the workflow simple:

```
telemetry.csv  ->  sptelemetry.analysis  ->  health_report.md
       ^                    |
       |                    v
  synthetic demo       EWMA + robust z + sustained-change heuristic
```

It focuses on common silicon photonics symptoms: receive-power loss, insertion-loss drift,
laser-bias growth, thermal-control saturation, supply sag, and BER margin collapse.

## Quickstart

```bash
pip install -r requirements.txt

# Generate deterministic sample telemetry with a fiber/connector loss signature
python -m sptelemetry.cli generate --out reports/telemetry.csv --scenario fiber_contamination

# Analyze a CSV and write a markdown report
python -m sptelemetry.cli analyze --input reports/telemetry.csv --out reports/health_report.md

# Or run both steps
python -m sptelemetry.cli demo --out-dir reports/demo --scenario laser_aging
```

## CSV schema

Input CSV files need these columns:

```text
timestamp,module_id,channel,tx_power_dbm,rx_power_dbm,laser_bias_ma,temperature_c,tec_current_a,voltage_v,ber,loss_db
```

`timestamp` accepts ISO-8601 values such as `2026-01-01T00:00:00Z`. Rows are streamed by the
loader, so large files do not need to be read into memory before analysis.

## Detection methods

- **EWMA residual:** compares each new value with the previous exponentially weighted moving
  average for that module/channel/metric.
- **Robust z-score:** compares each value with a rolling median and median absolute deviation,
  avoiding a fragile Gaussian assumption.
- **Sustained-change heuristic:** compares older and recent rolling medians in the direction
  considered risky for each metric.
- **Guardrails:** applies simple optical-module sanity bounds for temperature, supply voltage,
  BER, optical power, laser bias, TEC current, and insertion loss.

The report includes the top events, maintenance priority, per-metric snapshots, the
inferred failure mode, and a specific validation check to run next.

## Status

This is an MVP: deterministic generator, CSV loader, streaming analyzer, maintenance
priority ranking, markdown report, CLI, and network-free tests. Natural next steps are
CMIS register ingestion, per-module threshold profiles, and richer plotting.

## License

MIT - see [LICENSE](LICENSE).
