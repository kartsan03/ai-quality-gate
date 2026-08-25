import textwrap
from pathlib import Path

import pytest

from aiqg import __version__
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


def test_bad_path_exits_2_without_gate_failure(capsys):
    # A setup error must not look like a gate failure (exit 1) in CI.
    assert main(["run", "no/such/directory"]) == 2
    assert "error" in capsys.readouterr().err


def test_unknown_check_name_exits_2(tmp_path):
    case = make_passing_case(tmp_path / "tiny")
    text = case.read_text(encoding="utf-8")
    case.write_text(text + "  not_a_check: {}\n", encoding="utf-8")
    assert main(["run", str(case)]) == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_invalid_json_output_is_reported_not_crash(tmp_path, capsys):
    root = tmp_path / "tiny"
    make_passing_case(root)
    (root / "outputs" / "broken.json").write_text("{not json", encoding="utf-8")
    assert main(["run", str(root)]) == 1
    assert "invalid JSON" in capsys.readouterr().out


def test_html_report_created(tmp_path):
    case = make_passing_case(tmp_path / "tiny")
    report = tmp_path / "report.html"
    assert main(["run", str(case), "--html", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "tiny_case" in text and "checks passed" in text
