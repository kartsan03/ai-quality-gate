import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import jsonschema
import yaml

from . import checks


def _resolve_under(case_dir, rel, *, label):
    """Resolve rel under case_dir; reject absolute paths and .. escapes."""
    if rel is None or str(rel).strip() == "":
        raise ValueError(f"{label}: path must be a non-empty relative path")
    rel = str(rel)
    if Path(rel).is_absolute():
        raise ValueError(f"{label}: path must be relative to the case directory, got {rel!r}")
    if ".." in Path(rel).parts:
        raise ValueError(f"{label}: path escapes case directory: {rel!r}")
    case_root = case_dir.resolve()
    resolved = (case_dir / rel).resolve()
    try:
        resolved.relative_to(case_root)
    except ValueError as e:
        raise ValueError(f"{label}: path escapes case directory: {rel!r}") from e
    return resolved


def _glob_under(case_dir, pattern):
    if ".." in Path(pattern).parts:
        raise ValueError(f"outputs_glob: path escapes case directory: {pattern!r}")
    case_root = case_dir.resolve()
    files = []
    for path in sorted(case_dir.glob(pattern)):
        resolved = path.resolve()
        try:
            resolved.relative_to(case_root)
        except ValueError as e:
            raise ValueError(
                f"outputs_glob: matched path escapes case directory: {path.as_posix()}"
            ) from e
        files.append(path)
    return files


_CI_TRUTHY = {"1", "true", "TRUE", "yes"}


def _env_truthy(name):
    return os.environ.get(name, "") in _CI_TRUTHY


PER_OUTPUT = {
    "json_schema": checks.check_json_schema,
    "required_fields": checks.check_required_fields,
    "regex": checks.check_regex,
    "grounding": checks.check_grounding,
    "forbidden_phrases": checks.check_forbidden_phrases,
    "snapshot": checks.check_snapshot,
}

_CASE_SCHEMA = json.loads(
    resources.files("aiqg").joinpath("case_schema.json").read_text(encoding="utf-8")
)


@dataclass
class CheckResult:
    case: str
    check: str
    output_file: str
    failures: list


def _validate_case_schema(case, case_path):
    validator = jsonschema.Draft202012Validator(_CASE_SCHEMA)
    errors = sorted(validator.iter_errors(case), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    e = errors[0]
    path = ".".join(str(p) for p in e.absolute_path)
    where = f" ({path})" if path else ""
    raise ValueError(f"{case_path.as_posix()}: invalid case.yml{where}: {e.message}")


def load_case(case_path, *, load_snapshot=True):
    case_dir = case_path.parent
    try:
        case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"{case_path.as_posix()}: invalid YAML: {e}") from e
    if not isinstance(case, dict):
        raise ValueError(f"{case_path.as_posix()}: case file must be a YAML mapping")
    conf = case.get("checks") or {}
    if not isinstance(conf, dict):
        raise ValueError(f"{case_path.as_posix()}: checks must be a mapping")
    for check_name in list(conf):
        if conf[check_name] is None:
            conf[check_name] = {}
    case["checks"] = conf
    _validate_case_schema(case, case_path)
    if "schema_file" in conf.get("json_schema", {}):
        schema_path = _resolve_under(
            case_dir, conf["json_schema"]["schema_file"], label="schema_file"
        )
        conf["json_schema"]["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
    if load_snapshot and "file" in conf.get("snapshot", {}):
        snapshot_path = _resolve_under(
            case_dir, conf["snapshot"]["file"], label="snapshot.file"
        )
        conf["snapshot"]["expected"] = json.loads(snapshot_path.read_text(encoding="utf-8"))
    case["checks"] = conf
    source_path = _resolve_under(case_dir, case["source_file"], label="source_file")
    case["source"] = source_path.read_text(encoding="utf-8")
    case["output_files"] = _glob_under(case_dir, case["outputs_glob"])
    case["_case_dir"] = case_dir
    return case


def run_case(case_path):
    case = load_case(case_path)
    name = case["name"]
    if not case["output_files"]:
        raise FileNotFoundError(f"{case_path}: no outputs match {case['outputs_glob']!r}")

    results = []
    outputs = []
    for path in case["output_files"]:
        try:
            outputs.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as e:
            results.append(CheckResult(name, "json_parse", path.as_posix(), [f"invalid JSON: {e}"]))

    for check_name, conf in case["checks"].items():
        if check_name == "stability":
            continue
        fn = PER_OUTPUT[check_name]
        for path, data in outputs:
            results.append(CheckResult(name, check_name, path.as_posix(), fn(conf, data, case["source"])))

    if "stability" in case["checks"]:
        failures = checks.check_stability(case["checks"]["stability"], outputs)
        results.append(CheckResult(name, "stability", "(all outputs)", failures))
    return results


def find_cases(target):
    target = Path(target)
    if target.is_file():
        return [target]
    cases = sorted(target.rglob("case.yml"))
    if not cases:
        raise FileNotFoundError(f"no case.yml files under {target}")
    return cases


def refuse_snapshot_update_in_ci():
    if _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS"):
        raise ValueError(
            "refusing to update snapshots when CI or GITHUB_ACTIONS is set "
            "(truthy: 1, true, TRUE, yes)"
        )


def update_snapshots(target):
    """Rewrite snapshot expected files from the first recorded output of each case."""
    refuse_snapshot_update_in_ci()
    updated = []
    for case_path in find_cases(target):
        case = load_case(case_path, load_snapshot=False)
        snap = case["checks"].get("snapshot")
        if not snap or "file" not in snap:
            continue
        if not case["output_files"]:
            raise FileNotFoundError(
                f"{case_path}: no outputs match {case['outputs_glob']!r}"
            )
        data = json.loads(case["output_files"][0].read_text(encoding="utf-8"))
        dest = _resolve_under(case["_case_dir"], snap["file"], label="snapshot.file")
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        updated.append(dest.as_posix())
    return updated


def ingest_jsonl(source, out_dir, field=None):
    """Write one JSON file per JSONL line (or stdin) into out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if source == "-" or source is None:
        import sys
        lines = sys.stdin.read().splitlines()
    else:
        lines = Path(source).read_text(encoding="utf-8").splitlines()
    written = []
    n = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON on line {n + 1}: {e}") from e
        if field:
            value = checks.get_path(obj, field)
            if value is None:
                raise ValueError(f"line {n + 1}: field {field!r} not found")
            obj = value
        path = out / f"{n:04d}.json"
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path.as_posix())
        n += 1
    return written
