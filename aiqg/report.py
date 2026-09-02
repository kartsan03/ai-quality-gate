"""Static HTML report. No JS, one self-contained file.

Design: technical-mono, dense, styled like the CI log it accompanies.
Two semantic colors only (pass green, fail red); everything else is neutral.
"""

import html
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CSS = """
body { background: #101216; color: #c9d1d9; max-width: 66rem; margin: 2rem auto;
       padding: 0 1rem; font: 13px/1.55 ui-monospace, 'Cascadia Mono', Consolas,
       'Liberation Mono', monospace; }
h1 { font-size: 1.1rem; font-weight: 600; letter-spacing: .04em; margin: 0; }
h2 { font-size: .85rem; font-weight: 600; text-transform: uppercase;
     letter-spacing: .08em; color: #8b949e; margin: 2.2rem 0 .6rem; }
.meta { color: #8b949e; font-size: .8rem; margin: .2rem 0 1.4rem; }
.verdict { font-size: 1.6rem; font-weight: 700; letter-spacing: .05em;
           margin: 1.2rem 0 .2rem; }
.tiles { display: flex; gap: .6rem; flex-wrap: wrap; margin: 1rem 0 0; }
.tile { border: 1px solid #30363d; padding: .55rem .9rem; min-width: 6.5rem; }
.tile b { display: block; font-size: 1.35rem; font-weight: 600; }
.tile span { color: #8b949e; font-size: .75rem; text-transform: uppercase;
             letter-spacing: .06em; }
table { border-collapse: collapse; width: 100%; font-size: .8rem; }
th, td { text-align: left; padding: .3rem .55rem; border-bottom: 1px solid #21262d;
         vertical-align: top; }
th { color: #8b949e; font-weight: 400; text-transform: uppercase;
     letter-spacing: .06em; font-size: .7rem; }
td:first-child { width: 3.2rem; }
.pass { color: #3fb950; }
.fail { color: #f85149; }
ul.failures { margin: .25rem 0 .1rem; padding-left: 1.1rem; color: #e0938f;
              list-style: '- '; }
ul.failures li { margin: .1rem 0; }
"""


def _row(result):
    cls = "fail" if result.failures else "pass"
    status = "FAIL" if result.failures else "PASS"
    detail = ""
    if result.failures:
        items = "".join(f"<li>{html.escape(f)}</li>" for f in result.failures)
        detail = f'<ul class="failures">{items}</ul>'
    return (f'<tr><td class="{cls}">{status}</td><td>{html.escape(result.check)}</td>'
            f"<td>{html.escape(result.output_file)}{detail}</td></tr>")


def write_report(results, path):
    failed = [r for r in results if r.failures]
    cases = sorted({r.case for r in results})
    outputs = {r.output_file for r in results if r.output_file != "(all outputs)"}

    if failed:
        verdict = '<div class="verdict fail">GATE FAILED</div>'
    else:
        verdict = '<div class="verdict pass">GATE PASSED</div>'

    by_check = Counter(r.check for r in failed)
    if by_check:
        rows = "".join(f"<tr><td></td><td>{html.escape(k)}</td><td>{v} failed</td></tr>"
                       for k, v in by_check.most_common())
        failures_table = (f"<h2>Failures by validator</h2><table>"
                          f"<tr><th></th><th>validator</th><th>checks</th></tr>{rows}</table>")
    else:
        failures_table = '<h2>Failures by validator</h2><p class="pass">none</p>'

    sections = []
    for case in cases:
        case_results = [r for r in results if r.case == case]
        case_failed = sum(1 for r in case_results if r.failures)
        badge = (f'<span class="fail">{case_failed} failing</span>' if case_failed
                 else '<span class="pass">all passing</span>')
        rows = "".join(_row(r) for r in case_results)
        sections.append(f"<h2>{html.escape(case)} / {badge}</h2>"
                        f"<table><tr><th>status</th><th>check</th><th>output</th></tr>{rows}</table>")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Quality Gate report</title>
<style>{CSS}</style>
</head>
<body>
<h1>ai-quality-gate</h1>
<p class="meta">generated {generated}</p>
{verdict}
<div class="tiles">
<div class="tile"><b>{len(cases)}</b><span>cases</span></div>
<div class="tile"><b>{len(outputs)}</b><span>outputs</span></div>
<div class="tile"><b class="pass">{len(results) - len(failed)}</b><span>checks passed</span></div>
<div class="tile"><b class="fail">{len(failed)}</b><span>checks failed</span></div>
</div>
{failures_table}
{''.join(sections)}
</body>
</html>
"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


def write_junit(results, path):
    """JUnit XML so CI renders gate failures as annotated test results."""
    by_case = {}
    for r in results:
        by_case.setdefault(r.case, []).append(r)

    suites = []
    for case in sorted(by_case):
        rows = by_case[case]
        n_failed = sum(1 for r in rows if r.failures)
        testcases = []
        for r in rows:
            name = f"{r.check} [{r.output_file}]"
            if r.failures:
                detail = "\n".join(r.failures)
                testcases.append(
                    f'<testcase classname="{html.escape(case)}" name="{html.escape(name)}">'
                    f'<failure message="{html.escape(r.failures[0])}">'
                    f"{html.escape(detail)}</failure></testcase>"
                )
            else:
                testcases.append(
                    f'<testcase classname="{html.escape(case)}" name="{html.escape(name)}"/>'
                )
        suites.append(
            f'<testsuite name="{html.escape(case)}" tests="{len(rows)}" failures="{n_failed}">'
            + "".join(testcases)
            + "</testsuite>"
        )

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("<testsuites>" + "".join(suites) + "</testsuites>", encoding="utf-8")
