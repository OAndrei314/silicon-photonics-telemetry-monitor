from datetime import datetime, timezone

from sptelemetry.data import FIELDNAMES, generate_csv, generate_rows, iter_csv


def test_generate_rows_is_deterministic():
    first = generate_rows(samples=4, channels=2, seed=11)
    second = generate_rows(samples=4, channels=2, seed=11)

    assert first == second
    assert len(first) == 8
    assert first[0].timestamp == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_generate_and_load_csv_round_trip(tmp_path):
    path = tmp_path / "telemetry.csv"

    generate_csv(path, samples=3, channels=2, scenario="nominal", seed=3)
    rows = list(iter_csv(path))

    assert len(rows) == 6
    assert rows[0].module_id == "mod-01"
    assert rows[0].channel == 1
    assert set(path.read_text(encoding="utf-8").splitlines()[0].split(",")) == set(FIELDNAMES)
