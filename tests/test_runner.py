import textwrap
from pathlib import Path

from aiqg.cli import main

EXAMPLES = Path(__file__).parents[1] / "examples"


def make_passing_case(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "source.txt").write_text("Total due: 100 EUR", encoding="utf-8")
    (root / "outputs").mkdir()
    (root / "outputs" / "good.json").write_text('{"total": "100"}', encoding="utf-8")
    (root / "case.yml").write_text(textwrap.dedent("""\
        name: tiny_case
        task_type: extraction
        source_file: source.txt
        outputs_glob: outputs/*.json
        checks:
          required_fields:
            fields: [total]
          grounding:
            fields: [total]
        """), encoding="utf-8")
    return root / "case.yml"


def test_run_single_case_passes(tmp_path):
    case = make_passing_case(tmp_path / "tiny")
    assert main(["run", str(case)]) == 0


def test_run_directory_of_cases(tmp_path):
    make_passing_case(tmp_path / "case_a")
    make_passing_case(tmp_path / "case_b")
    assert main(["run", str(tmp_path)]) == 0


def test_passing_examples_exit_0():
    assert main(["run", str(EXAMPLES / "passing")]) == 0


def test_failing_case_returns_exit_code_1():
    assert main(["run", str(EXAMPLES / "regressions" / "invoice_extraction" / "case.yml")]) == 1


def test_html_report_created(tmp_path):
    case = make_passing_case(tmp_path / "tiny")
    report = tmp_path / "report.html"
    assert main(["run", str(case), "--html", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "tiny_case" in text and "checks passed" in text
