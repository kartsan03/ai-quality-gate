import json
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class CheckResult:
    case: str
    check: str
    output_file: str
    failures: list


def load_case(case_path):
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
    known = set(PER_OUTPUT) | {"stability"}
    for check_name in conf:
        if check_name not in known:
            raise ValueError(f"{case_path.as_posix()}: unknown check {check_name!r}")
        if conf[check_name] is None:
            conf[check_name] = {}
    if "json_schema" in conf and not {"schema", "schema_file"} & conf["json_schema"].keys():
        raise ValueError(f"{case_path.as_posix()}: json_schema requires 'schema_file' or an inline 'schema'")
    if "snapshot" in conf and not {"expected", "file"} & conf["snapshot"].keys():
        raise ValueError(f"{case_path.as_posix()}: snapshot requires 'file' or an inline 'expected'")
    for check_name in ("required_fields", "regex", "stability"):
        if check_name in conf and "fields" not in conf[check_name]:
            raise ValueError(f"{case_path.as_posix()}: {check_name} requires 'fields'")
    if "schema_file" in conf.get("json_schema", {}):
        schema_path = case_dir / conf["json_schema"]["schema_file"]
        conf["json_schema"]["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
    if "file" in conf.get("snapshot", {}):
        snapshot_path = case_dir / conf["snapshot"]["file"]
        conf["snapshot"]["expected"] = json.loads(snapshot_path.read_text(encoding="utf-8"))
    case["checks"] = conf
    case["source"] = (case_dir / case["source_file"]).read_text(encoding="utf-8")
    case["output_files"] = sorted(case_dir.glob(case["outputs_glob"]))
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
