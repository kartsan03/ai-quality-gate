import json
import os
import textwrap
from pathlib import Path

import pytest

from aiqg.cli import main
from aiqg.runner import refuse_snapshot_update_in_ci

EXAMPLES = Path(__file__).parents[1] / "examples"


def make_snapshot_case(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "source.txt").write_text("Total due: 100 EUR", encoding="utf-8")
    (root / "outputs").mkdir()
    (root / "outputs" / "good.json").write_text(
        json.dumps({"total": "100", "confidence": 0.9}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "expected.json").write_text(
        json.dumps({"total": "99", "confidence": 0.1}, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "case.yml").write_text(textwrap.dedent("""\
        name: snap_case
        task_type: extraction
        source_file: source.txt
        outputs_glob: outputs/*.json
        checks:
          snapshot:
            file: expected.json
            ignore: [confidence]
        """), encoding="utf-8")
    return root


def test_snapshot_update_local(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = make_snapshot_case(tmp_path / "snap")
    assert main(["run", str(root)]) == 1
    assert main(["snapshot", "--update", str(root)]) == 0
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    assert expected["total"] == "100"
    assert "confidence" not in expected  # ignore keys dropped like check_snapshot
    assert main(["run", str(root)]) == 0


def test_run_update_snapshots_local(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = make_snapshot_case(tmp_path / "snap")
    assert main(["run", str(root), "--update-snapshots"]) == 0
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    assert expected["total"] == "100"
    assert "confidence" not in expected


@pytest.mark.parametrize("env", ["CI", "GITHUB_ACTIONS"])
def test_snapshot_update_denied_in_ci(tmp_path, monkeypatch, env, capsys):
    monkeypatch.setenv(env, "true")
    other = "GITHUB_ACTIONS" if env == "CI" else "CI"
    monkeypatch.delenv(other, raising=False)
    root = make_snapshot_case(tmp_path / "snap")
    assert main(["snapshot", "--update", str(root)]) == 2
    err = capsys.readouterr().err
    assert "refusing to update snapshots" in err
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    assert expected["total"] == "99"


def test_run_update_snapshots_denied_in_ci(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = make_snapshot_case(tmp_path / "snap")
    assert main(["run", str(root), "--update-snapshots"]) == 2
    assert "refusing to update snapshots" in capsys.readouterr().err


def test_refuse_helper_only_true(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    refuse_snapshot_update_in_ci()
    monkeypatch.setenv("CI", "1")  # not exactly "true"
    refuse_snapshot_update_in_ci()


def test_ingest_jsonl_file(tmp_path):
    src = tmp_path / "logs.jsonl"
    src.write_text(
        '{"response": {"total": "1"}}\n'
        '{"response": {"total": "2"}}\n',
        encoding="utf-8",
    )
    out = tmp_path / "outputs"
    assert main(["ingest", str(src), "--out", str(out), "--jsonpath", "response"]) == 0
    files = sorted(out.glob("*.json"))
    assert [p.name for p in files] == ["0001.json", "0002.json"]
    assert json.loads(files[0].read_text(encoding="utf-8")) == {"total": "1"}
    assert json.loads(files[1].read_text(encoding="utf-8")) == {"total": "2"}


def test_ingest_field_alias(tmp_path):
    src = tmp_path / "logs.jsonl"
    src.write_text('{"response": {"total": "7"}}\n', encoding="utf-8")
    out = tmp_path / "out"
    assert main(["ingest", str(src), "--out", str(out), "--field", "response"]) == 0
    assert json.loads((out / "0001.json").read_text(encoding="utf-8")) == {"total": "7"}


def test_ingest_whole_line(tmp_path):
    src = tmp_path / "logs.jsonl"
    src.write_text('{"total": "7"}\n', encoding="utf-8")
    out = tmp_path / "out"
    assert main(["ingest", str(src), "--out", str(out)]) == 0
    assert json.loads((out / "0001.json").read_text(encoding="utf-8")) == {"total": "7"}


def test_ingest_missing_jsonpath_exits_2(tmp_path, capsys):
    src = tmp_path / "logs.jsonl"
    src.write_text('{"other": 1}\n', encoding="utf-8")
    assert main(["ingest", str(src), "--out", str(tmp_path / "o"), "--jsonpath", "response"]) == 2
    assert "not found" in capsys.readouterr().err


def test_ingest_empty_exits_2(tmp_path, capsys):
    src = tmp_path / "empty.jsonl"
    src.write_text("\n\n", encoding="utf-8")
    assert main(["ingest", str(src), "--out", str(tmp_path / "o")]) == 2
    assert "no JSON objects" in capsys.readouterr().err


def test_schema_rejects_extra_top_level_key(tmp_path, capsys):
    root = tmp_path / "tiny"
    root.mkdir()
    (root / "source.txt").write_text("Total due: 100 EUR", encoding="utf-8")
    (root / "outputs").mkdir()
    (root / "outputs" / "a.json").write_text('{"total": "100"}', encoding="utf-8")
    (root / "case.yml").write_text(textwrap.dedent("""\
        name: bad
        source_file: source.txt
        outputs_glob: outputs/*.json
        checks:
          required_fields:
            fields: [total]
        unexpected_key: true
        """), encoding="utf-8")
    assert main(["run", str(root)]) == 2
    assert "invalid case.yml" in capsys.readouterr().err


def test_schema_rejects_empty_name(tmp_path, capsys):
    root = tmp_path / "tiny"
    root.mkdir()
    (root / "source.txt").write_text("x", encoding="utf-8")
    (root / "outputs").mkdir()
    (root / "outputs" / "a.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "case.yml").write_text(textwrap.dedent("""\
        name: ""
        source_file: source.txt
        outputs_glob: outputs/*.json
        checks:
          required_fields:
            fields: [a]
        """), encoding="utf-8")
    assert main(["run", str(root)]) == 2
    assert "invalid case.yml" in capsys.readouterr().err


def test_exit_0_passing_examples():
    assert main(["run", str(EXAMPLES / "passing")]) == 0


def test_exit_1_regression_examples():
    assert main(["run", str(EXAMPLES / "regressions")]) == 1


def test_exit_2_setup_error(capsys):
    assert main(["run", "no/such/path"]) == 2
    assert "error" in capsys.readouterr().err
