from sptelemetry.analysis import analyze_rows
from sptelemetry.data import generate_rows
from sptelemetry.report import build_health_report


def test_report_contains_diagnosis_and_methods():
    rows = generate_rows(samples=140, channels=4, scenario="thermal_runaway", seed=9)
    result = analyze_rows(rows)

    report = build_health_report(result, source="synthetic.csv", rows=rows)

    assert "# Silicon Photonics Telemetry Health Report" in report
    assert "Likely failure mode" in report
    assert "Thermal-control" in report
    assert "EWMA residuals" in report
    assert "robust z" in report
