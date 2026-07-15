from pathlib import Path

from aiqg import checks


def test_json_schema():
    schema = {"type": "object", "required": ["total"], "properties": {"total": {"type": "string"}}}
    assert checks.check_json_schema({"schema": schema}, {"total": "5"}, "") == []
    assert checks.check_json_schema({"schema": schema}, {"total": 5}, "")
    assert checks.check_json_schema({"schema": schema}, {}, "")


def test_grounding_catches_hallucinated_value():
    source = "Total due: 5,868.50 EUR"
    conf = {"fields": ["total"]}
    assert checks.check_grounding(conf, {"total": "5,868.50"}, source) == []
    assert checks.check_grounding(conf, {"total": "5868.50"}, source) == []
    failures = checks.check_grounding(conf, {"total": "6,868.50"}, source)
    assert failures and "not found in source" in failures[0]


def test_grounding_numbers_and_citations():
    source = "Refunds are processed within 14 days."
    conf = {"numbers_in": ["answer"], "require_citations": "citations"}
    good = {"answer": "within 14 days", "citations": ["kb-1"]}
    bad = {"answer": "within 30 days", "citations": []}
    wrong_type = {"answer": "within 14 days", "citations": "kb-1"}
    assert checks.check_grounding(conf, good, source) == []
    failures = checks.check_grounding(conf, bad, source)
    assert any("number '30'" in f for f in failures)
    assert any("no citations" in f for f in failures)
    assert checks.check_grounding(conf, wrong_type, source) == ["grounding: no citations in citations"]


def test_forbidden_phrases_default_list():
    output = {"summary": "As an AI language model, I cannot help."}  # intentional fixture
    assert checks.check_forbidden_phrases({}, output, "")
    assert checks.check_forbidden_phrases({}, {"summary": "Plain summary."}, "") == []


def test_snapshot_ignores_configured_fields():
    conf = {"expected": {"total": "5"}, "ignore": ["confidence"]}
    assert checks.check_snapshot(conf, {"total": "5", "confidence": 0.4}, "") == []
    failures = checks.check_snapshot(conf, {"total": "6", "confidence": 0.4}, "")
    assert failures == ["snapshot: total: expected '5', got '6'"]


def test_stability_catches_inconsistent_critical_field():
    conf = {"fields": ["category"]}
    stable = [(Path("a.json"), {"category": "bug"}), (Path("b.json"), {"category": "bug"})]
    flappy = [(Path("a.json"), {"category": "bug"}), (Path("b.json"), {"category": "billing"})]
    assert checks.check_stability(conf, stable) == []
    failures = checks.check_stability(conf, flappy)
    assert failures and "category differs" in failures[0]
