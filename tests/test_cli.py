from pathlib import Path

from sptelemetry.cli import main


def test_cli_generate_and_analyze(tmp_path):
    csv_path = tmp_path / "telemetry.csv"
    report_path = tmp_path / "report.md"

    assert main(["generate", "--out", str(csv_path), "--samples", "48", "--scenario", "laser_aging"]) == 0
    assert csv_path.exists()

    assert main(["analyze", "--input", str(csv_path), "--out", str(report_path)]) == 0
    report = Path(report_path).read_text(encoding="utf-8")
    assert "Silicon Photonics Telemetry Health Report" in report
    assert "Next validation check" in report
