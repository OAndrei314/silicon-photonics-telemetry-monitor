from sptelemetry.analysis import AnalysisConfig, analyze_rows
from sptelemetry.data import generate_rows
from sptelemetry.diagnosis import infer_health, maintenance_priority


def test_nominal_stream_stays_nominal():
    rows = generate_rows(samples=80, channels=2, scenario="nominal", seed=5)

    result = analyze_rows(rows)
    status, likely_mode, _next_check = infer_health(result.events, result.summaries)

    assert status in {"nominal", "watch"}
    assert len([event for event in result.events if event.severity == "critical"]) == 0
    assert "No actionable" in likely_mode or "Slow parametric drift" in likely_mode


def test_fiber_contamination_points_to_receive_loss():
    rows = generate_rows(samples=140, channels=4, scenario="fiber_contamination", seed=2)

    result = analyze_rows(rows)
    status, likely_mode, next_check = infer_health(result.events, result.summaries)
    metrics = {event.metric for event in result.events}

    assert status in {"degraded", "critical"}
    assert "contamination" in likely_mode
    assert "endfaces" in next_check
    assert {"rx_power_dbm", "loss_db"} <= metrics

    priorities = maintenance_priority(result.events)
    assert priorities
    priority_metrics = {row["primary_metric"] for row in priorities}
    assert priority_metrics & {"rx_power_dbm", "loss_db", "ber"}
    assert any("fiber" in row["recommended_action"] or "connector" in row["recommended_action"] for row in priorities)


def test_laser_aging_points_to_bias_headroom():
    rows = generate_rows(samples=160, channels=4, scenario="laser_aging", seed=4)

    result = analyze_rows(rows, AnalysisConfig(robust_window=24))
    _status, likely_mode, next_check = infer_health(result.events, result.summaries)

    assert "Laser aging" in likely_mode
    assert "L-I sweep" in next_check


def test_power_rail_flags_voltage_events():
    rows = generate_rows(samples=120, channels=2, scenario="power_rail", seed=8)

    result = analyze_rows(rows)
    _status, likely_mode, next_check = infer_health(result.events, result.summaries)

    assert "Power-rail" in likely_mode
    assert "Scope" in next_check
