import argparse
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .report import write_junit, write_report
from .runner import find_cases, ingest_jsonl, run_case, update_snapshots

CASE_TEMPLATE = r"""name: {name}
task_type: extraction
source_file: source.txt
outputs_glob: outputs/*.json
checks:
  required_fields:
    fields: [total]
  grounding:
    fields: [total]              # value must appear in source.txt
  # regex:
  #   fields:
  #     order_id: '^ORD-\d{4}$'
  # forbidden_phrases: {}        # {} uses the built-in phrase list
  # json_schema:
  #   schema_file: schema.json
  # snapshot:
  #   file: expected.json
  #   ignore: [confidence, generated_at]
  # stability:
  #   fields: [total]
"""


def scaffold_case(directory):
    target = Path(directory)
    case_file = target / "case.yml"
    if case_file.exists():
        raise ValueError(f"refusing to overwrite existing {case_file.as_posix()}")
    (target / "outputs").mkdir(parents=True, exist_ok=True)
    (target / "source.txt").write_text("Total due: 100 EUR\n", encoding="utf-8")
    (target / "outputs" / "good.json").write_text('{"total": "100"}\n', encoding="utf-8")
    case_file.write_text(CASE_TEMPLATE.replace("{name}", target.name), encoding="utf-8")
    return case_file


def _print_results(results):
    failed = [r for r in results if r.failures]
    for r in results:
        status = "FAIL" if r.failures else "PASS"
        print(f"{status}  {r.case}  {r.check}  {r.output_file}")
        for failure in r.failures:
            print(f"      - {failure}")

    cases = {r.case for r in results}
    outputs = {r.output_file for r in results if r.output_file != "(all outputs)"}
    print(f"\n{len(cases)} cases, {len(outputs)} outputs, "
          f"{len(results) - len(failed)} checks passed, {len(failed)} failed")
    if failed:
        by_check = Counter(r.check for r in failed)
        print("failures by check: " + ", ".join(f"{k}={v}" for k, v in by_check.most_common()))
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aiqg", description="Quality gate for recorded AI outputs.")
    parser.add_argument("--version", action="version", version=f"aiqg {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run all checks for a case file or a directory of cases")
    run.add_argument("target", help="a case.yml file or a directory containing cases")
    run.add_argument("--html", metavar="FILE", help="write a static HTML report to FILE")
    run.add_argument("--junit", metavar="FILE",
                     help="write a JUnit XML report to FILE (CI renders gate failures as annotated test results)")
    run.add_argument("--update-snapshots", action="store_true",
                     help="rewrite snapshot expected files from recorded outputs (refused in CI)")

    init = sub.add_parser("init", help="scaffold a working example case, then edit it into your own")
    init.add_argument("directory", help="directory to create the case in")

    snap = sub.add_parser("snapshot", help="manage approved snapshot files")
    snap.add_argument("--update", action="store_true", required=True,
                      help="rewrite snapshot expected files from recorded outputs (refused in CI)")
    snap.add_argument("target", help="a case.yml file or a directory containing cases")

    ingest = sub.add_parser("ingest", help="turn JSONL (or stdin) into outputs/*.json files")
    ingest.add_argument("source", nargs="?", default="-",
                        help="JSONL file, or '-' for stdin (default)")
    ingest.add_argument("--out", default="outputs",
                        help="directory to write JSON files into (default: outputs)")
    ingest.add_argument("--field", metavar="PATH",
                        help="dotted path of the JSON value to keep from each line")

    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            case_file = scaffold_case(args.directory)
        except ValueError as e:
            print(f"aiqg: error: {e}", file=sys.stderr)
            return 2
        print(f"created {case_file.as_posix()}, source.txt, outputs/good.json")
        print("the scaffolded case runs green as-is:")
        print(f"  aiqg run {Path(args.directory).as_posix()}")
        print("then replace source.txt and outputs/ with your recorded data and edit the checks.")
        return 0

    if args.command == "ingest":
        try:
            written = ingest_jsonl(args.source, args.out, field=args.field)
        except (OSError, ValueError) as e:
            print(f"aiqg: error: {e}", file=sys.stderr)
            return 2
        if not written:
            print("aiqg: error: no JSON objects found", file=sys.stderr)
            return 2
        print(f"wrote {len(written)} file(s) to {Path(args.out).as_posix()}")
        for path in written:
            print(f"  {path}")
        return 0

    if args.command == "snapshot" or (args.command == "run" and args.update_snapshots):
        target = args.target
        try:
            updated = update_snapshots(target)
        except (FileNotFoundError, ValueError, OSError) as e:
            print(f"aiqg: error: {e}", file=sys.stderr)
            return 2
        if not updated:
            print("no snapshot files to update")
            return 0
        print(f"updated {len(updated)} snapshot file(s):")
        for path in updated:
            print(f"  {path}")
        if args.command == "snapshot":
            return 0
        # fall through to run after updating

    try:
        case_paths = find_cases(args.target)
        results = []
        for case_path in case_paths:
            results.extend(run_case(case_path))
    except (FileNotFoundError, ValueError) as e:
        # Setup errors are not gate failures: exit 2 keeps 1 unambiguous in CI.
        print(f"aiqg: error: {e}", file=sys.stderr)
        return 2

    failed = _print_results(results)

    if args.html:
        write_report(results, args.html)
        print(f"report written to {args.html}")
    if args.junit:
        write_junit(results, args.junit)
        print(f"junit report written to {args.junit}")
    return 1 if failed else 0
