import argparse
from collections import Counter

from .report import write_report
from .runner import find_cases, run_case


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aiqg", description="Quality gate for recorded AI outputs.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run all checks for a case file or a directory of cases")
    run.add_argument("target", help="a case.yml file or a directory containing cases")
    run.add_argument("--html", metavar="FILE", help="write a static HTML report to FILE")
    args = parser.parse_args(argv)

    results = []
    for case_path in find_cases(args.target):
        results.extend(run_case(case_path))

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

    if args.html:
        write_report(results, args.html)
        print(f"report written to {args.html}")
    return 1 if failed else 0
