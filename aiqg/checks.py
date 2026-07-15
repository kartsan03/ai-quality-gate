"""Validators.

Per-output checks take (config, output, source) and return a list of failure
strings; an empty list means the check passed. check_stability is the one
exception: it runs once per case across all recorded outputs.
"""

import json
import re

import jsonschema

DEFAULT_FORBIDDEN_PHRASES = [
    "as an ai language model",  # intentional target phrase for this validator
    "as a language model",
    "as an ai assistant",
    "i don't have enough information",
    "i do not have enough information",
    "i cannot assist with",
]


def get_path(data, path):
    """Look up a dotted path like 'customer.name'. Returns None if any hop is missing."""
    for key in path.split("."):
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _norm(value):
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def _strip_separators(text):
    return re.sub(r"[,$€ ]", "", text)


def _in_source(value, source):
    # ponytail: naive substring containment. Catches copied-vs-invented values,
    # not paraphrase. Move to word-boundary matching if short values false-positive.
    v, src = _norm(value), _norm(source)
    if v and v in src:
        return True
    v = _strip_separators(v)
    return bool(v) and v in _strip_separators(src)


def check_json_schema(config, output, source):
    validator = jsonschema.Draft202012Validator(config["schema"])
    return [f"schema: {e.json_path}: {e.message}" for e in validator.iter_errors(output)]


def check_required_fields(config, output, source):
    failures = []
    for field in config["fields"]:
        value = get_path(output, field)
        if value is None or value == "" or value == []:
            failures.append(f"required field missing or empty: {field}")
    return failures


def check_regex(config, output, source):
    failures = []
    for field, pattern in config["fields"].items():
        value = get_path(output, field)
        if value is None:
            failures.append(f"regex: field missing: {field}")
        elif not re.search(pattern, str(value)):
            failures.append(f"regex: {field}={value!r} does not match {pattern!r}")
    return failures


def check_grounding(config, output, source):
    failures = []
    for field in config.get("fields", []):
        value = get_path(output, field)
        if value is None:
            failures.append(f"grounding: field missing: {field}")
        elif not _in_source(value, source):
            failures.append(f"grounding: {field}={value!r} not found in source")
    for field in config.get("numbers_in", []):
        text = str(get_path(output, field) or "")
        for number in re.findall(r"\d[\d,.]*\d|\d", text):
            if not _in_source(number, source):
                failures.append(f"grounding: number {number!r} in {field} not found in source")
    citation_field = config.get("require_citations")
    if citation_field:
        citations = get_path(output, citation_field)
        if not isinstance(citations, list) or not citations:
            failures.append(f"grounding: no citations in {citation_field}")
    return failures


def _string_values(data):
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from _string_values(value)
    elif isinstance(data, list):
        for value in data:
            yield from _string_values(value)


def check_forbidden_phrases(config, output, source):
    phrases = config.get("phrases", DEFAULT_FORBIDDEN_PHRASES)
    failures = []
    for text in _string_values(output):
        low = text.lower()
        failures += [f"forbidden phrase {p!r} in output" for p in phrases if p.lower() in low]
    return failures


def _drop_keys(data, keys):
    if isinstance(data, dict):
        return {k: _drop_keys(v, keys) for k, v in data.items() if k not in keys}
    if isinstance(data, list):
        return [_drop_keys(v, keys) for v in data]
    return data


def _diff(expected, got, path=""):
    if isinstance(expected, dict) and isinstance(got, dict):
        lines = []
        for key in sorted(set(expected) | set(got)):
            sub = f"{path}.{key}" if path else key
            if key not in got:
                lines.append(f"{sub}: missing (expected {expected[key]!r})")
            elif key not in expected:
                lines.append(f"{sub}: unexpected value {got[key]!r}")
            else:
                lines.extend(_diff(expected[key], got[key], sub))
        return lines
    if expected != got:
        return [f"{path or 'value'}: expected {expected!r}, got {got!r}"]
    return []


def check_snapshot(config, output, source):
    ignore = set(config.get("ignore", []))
    diffs = _diff(_drop_keys(config["expected"], ignore), _drop_keys(output, ignore))
    return [f"snapshot: {d}" for d in diffs]


def check_stability(config, outputs):
    """outputs is a list of (path, parsed_json) for every recorded output of the case."""
    failures = []
    for field in config["fields"]:
        seen = [(path.name, get_path(data, field)) for path, data in outputs]
        if len({json.dumps(value, sort_keys=True) for _, value in seen}) > 1:
            detail = ", ".join(f"{name}={value!r}" for name, value in seen)
            failures.append(f"stability: {field} differs across outputs: {detail}")
    return failures
