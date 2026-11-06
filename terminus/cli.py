"""Command line entry point for the protocol scaffold.

Section 5's protocol as two commands:

  run       run a matrix fixture end to end and write rows.jsonl plus summary.json
            (dry run by default: scripted adapters only)
  selftest  run the scaffold's invariant checks without pytest and exit on the result

The dry run is the default and the honest default. --live constructs the refusing
live stub and still refuses without explicit configuration; no subject was run in
building this scaffold.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from .driver import default_raters, run_matrix
from .fixtures import FixtureError, load_matrix


def _stamp(message: str) -> str:
    return f"[{time.strftime('%H:%M:%S')}] {message}"


def cmd_run(args) -> int:
    """Run a matrix fixture (Section 5)."""
    try:
        matrix = load_matrix(args.matrix)
    except FixtureError as error:
        print(_stamp(f"fixture refused: {error}"), file=sys.stderr)
        return 2
    if args.live and args.dry_run:
        print(_stamp("--dry-run and --live are mutually exclusive"), file=sys.stderr)
        return 2
    if not args.live:
        print(_stamp("dry run: scripted adapters only, no network call"))
    try:
        result = run_matrix(matrix, args.out, raters=default_raters(), live=args.live)
    except Exception as error:  # adapter refusals and script gaps are honest failures
        print(_stamp(f"run refused: {type(error).__name__}: {error}"), file=sys.stderr)
        return 2
    summary = result.summary
    print(_stamp(f"cells={len(summary['cells'])} subjects={summary['n_subjects']}"))
    print(_stamp(f"rows   -> {result.rows_path}"))
    print(_stamp(f"summary-> {result.summary_path}"))
    prereg = summary.get("preregistration")
    if prereg:
        print(_stamp(f"preregistration {prereg['verdict']}: {prereg['detail']}"))
        for cell in prereg["cells"]:
            print(_stamp(f"  {cell['cell_id']}: {cell['verdict']} ({cell['detail']})"))
    for name, verdict in summary["falsifiers"].items():
        print(_stamp(f"falsifier {name}: {verdict['verdict']} ({verdict['detail']})"))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_selftest(args) -> int:
    """Run the scaffold's invariant checks (stdlib only, no pytest)."""
    from .selftest import run_checks

    results = run_checks()
    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(_stamp(f"{status} {name}: {detail}"))
        if not ok:
            failed += 1
    print(_stamp(f"selftest: {len(results) - failed}/{len(results)} checks passed"))
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="terminus", description="Paper 1 discriminator protocol scaffold (Section 5)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a matrix fixture")
    run.add_argument("--matrix", required=True, help="path to a matrix JSON fixture")
    run.add_argument("--out", default="runs/scaffold", help="output directory for rows and summary")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="force scripted adapters only (the default path; named so it is explicit)",
    )
    run.add_argument(
        "--live",
        action="store_true",
        help="construct the live adapter stub (it refuses without explicit configuration)",
    )
    run.add_argument("--json", action="store_true", help="print the summary JSON to stdout")
    run.set_defaults(func=cmd_run)

    selftest = sub.add_parser("selftest", help="run the invariant checks without pytest")
    selftest.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)

