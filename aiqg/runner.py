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
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    conf = case.get("checks") or {}
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
            results.append(CheckResult(name, "json_parse", str(path), [f"invalid JSON: {e}"]))

    for check_name, conf in case["checks"].items():
        if check_name == "stability":
            continue
        fn = PER_OUTPUT.get(check_name)
        if fn is None:
            raise ValueError(f"{case_path}: unknown check {check_name!r}")
        for path, data in outputs:
            results.append(CheckResult(name, check_name, str(path), fn(conf, data, case["source"])))

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
