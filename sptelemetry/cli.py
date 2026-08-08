"""Command-line entry point: `python -m sptelemetry.cli generate|analyze ...`"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import AnalysisConfig, analyze_rows
from .data import generate_csv, iter_csv
from .report import build_health_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sptelemetry")
    sub = parser.add_subparsers(dest="command", required=True)

    gen_p = sub.add_parser("generate", help="generate deterministic CSV telemetry")
    gen_p.add_argument("--out", required=True, help="output CSV path")
    gen_p.add_argument("--samples", type=int, default=240, help="time samples per channel")
    gen_p.add_argument("--modules", type=int, default=1, help="number of modules")
    gen_p.add_argument("--channels", type=int, default=4, help="channels per module")
    gen_p.add_argument("--interval-seconds", type=int, default=30, help="seconds between samples")
    gen_p.add_argument(
        "--scenario",
        default="nominal",
        choices=["nominal", "fiber_contamination", "laser_aging", "thermal_runaway", "power_rail"],
        help="telemetry scenario to synthesize",
    )
    gen_p.add_argument("--seed", type=int, default=7, help="random seed")

    analyze_p = sub.add_parser("analyze", help="analyze CSV telemetry and write a markdown report")
    analyze_p.add_argument("--input", required=True, help="input CSV path")
    analyze_p.add_argument("--out", required=True, help="output markdown report path")
    analyze_p.add_argument("--ewma-alpha", type=float, default=0.2, help="EWMA smoothing factor")
    analyze_p.add_argument("--robust-window", type=int, default=32, help="rolling robust baseline window")
    analyze_p.add_argument("--robust-z-threshold", type=float, default=4.0, help="robust z event threshold")
    analyze_p.add_argument("--change-window", type=int, default=8, help="rolling window for drift heuristic")
    analyze_p.add_argument("--max-events", type=int, default=12, help="top events to include in the report")

    demo_p = sub.add_parser("demo", help="generate sample telemetry and its markdown report")
    demo_p.add_argument("--out-dir", default="reports/demo", help="directory for demo CSV and report")
    demo_p.add_argument(
        "--scenario",
        default="fiber_contamination",
        choices=["nominal", "fiber_contamination", "laser_aging", "thermal_runaway", "power_rail"],
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "generate":
            generate_csv(
                args.out,
                samples=args.samples,
                modules=args.modules,
                channels=args.channels,
                interval_seconds=args.interval_seconds,
                scenario=args.scenario,
                seed=args.seed,
            )
            print(f"wrote telemetry CSV -> {args.out}")
            return 0

        if args.command == "analyze":
            return _analyze_command(args)

        if args.command == "demo":
            out_dir = Path(args.out_dir)
            csv_path = out_dir / "telemetry.csv"
            report_path = out_dir / "health_report.md"
            generate_csv(csv_path, scenario=args.scenario)
            analyze_args = argparse.Namespace(
                input=str(csv_path),
                out=str(report_path),
                ewma_alpha=0.2,
                robust_window=32,
                robust_z_threshold=4.0,
                change_window=8,
                max_events=12,
            )
            code = _analyze_command(analyze_args)
            if code == 0:
                print(f"wrote demo artifacts -> {out_dir}")
            return code
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 1


def _analyze_command(args: argparse.Namespace) -> int:
    config = AnalysisConfig(
        ewma_alpha=args.ewma_alpha,
        robust_window=args.robust_window,
        robust_z_threshold=args.robust_z_threshold,
        change_window=args.change_window,
    )
    first_timestamp = None
    last_timestamp = None

    def tracked_rows():
        nonlocal first_timestamp, last_timestamp
        for row in iter_csv(args.input):
            if first_timestamp is None:
                first_timestamp = row.timestamp
            last_timestamp = row.timestamp
            yield row

    result = analyze_rows(tracked_rows(), config)
    time_span = None
    if first_timestamp is not None and last_timestamp is not None:
        time_span = (first_timestamp, last_timestamp)
    report = build_health_report(
        result,
        source=args.input,
        config=config,
        time_span=time_span,
        max_events=args.max_events,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote health report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
