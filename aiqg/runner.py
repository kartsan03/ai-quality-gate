import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import jsonschema
import yaml

from . import checks

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
    for key in ("name", "source_file", "outputs_glob"):
        if key not in case:
            raise ValueError(f"{case_path.as_posix()}: missing required key {key!r}")
    conf = case.get("checks") or {}
    if not isinstance(conf, dict):
        raise ValueError(f"{case_path.as_posix()}: checks must be a mapping")
    known = set(PER_OUTPUT) | {"stability"}
    for check_name in conf:
        if check_name not in known:
            raise ValueError(f"{case_path.as_posix()}: unknown check {check_name!r}")
        if conf[check_name] is None:
            conf[check_name] = {}
    if "json_schema" in conf and not {"schema", "schema_file"} & conf["json_schema"].keys():
        raise ValueError(
            f"{case_path.as_posix()}: json_schema requires 'schema_file' or an inline 'schema'"
        )
    if "snapshot" in conf and not {"expected", "file"} & conf["snapshot"].keys():
        raise ValueError(
            f"{case_path.as_posix()}: snapshot requires 'file' or an inline 'expected'"
        )
    for check_name in ("required_fields", "regex", "stability"):
        if check_name in conf and "fields" not in conf[check_name]:
            raise ValueError(f"{case_path.as_posix()}: {check_name} requires 'fields'")
    case["checks"] = conf
    _validate_case_schema(case, case_path)
    if "schema_file" in conf.get("json_schema", {}):
        schema_path = case_dir / conf["json_schema"]["schema_file"]
        conf["json_schema"]["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
    if load_snapshot and "file" in conf.get("snapshot", {}):
        snapshot_path = case_dir / conf["snapshot"]["file"]
        conf["snapshot"]["expected"] = json.loads(snapshot_path.read_text(encoding="utf-8"))
    case["checks"] = conf
    case["source"] = (case_dir / case["source_file"]).read_text(encoding="utf-8")
    case["output_files"] = sorted(case_dir.glob(case["outputs_glob"]))
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
    if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise ValueError(
            "refusing to update snapshots when CI=true or GITHUB_ACTIONS=true"
        )


def update_snapshots(target):
    """Rewrite snapshot expected files from the first parseable recorded output.

    Ignored keys are dropped consistently with check_snapshot before writing.
    """
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
        data = None
        for path in case["output_files"]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            raise ValueError(f"{case_path}: no parseable JSON outputs to update from")
        ignore = set(snap.get("ignore", []))
        to_write = checks._drop_keys(data, ignore)
        dest = case["_case_dir"] / snap["file"]
        dest.write_text(
            json.dumps(to_write, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        updated.append(dest.as_posix())
    return updated


def ingest_jsonl(source, out_dir, jsonpath=None):
    """Write one JSON file per JSONL line (or stdin) into out_dir as 0001.json…"""
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
        n += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON on line {n}: {e}") from e
        if jsonpath:
            value = checks.get_path(obj, jsonpath)
            if value is None:
                raise ValueError(f"line {n}: jsonpath {jsonpath!r} not found")
            obj = value
        path = out / f"{n:04d}.json"
        path.write_text(
            json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path.as_posix())
    return written
