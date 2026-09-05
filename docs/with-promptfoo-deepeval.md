# Using aiqg with promptfoo and DeepEval

promptfoo and DeepEval call models and score outputs. aiqg does neither: it
gates recorded JSON you already have. Use them together by recording once,
then letting aiqg enforce deterministic rules in CI. aiqg has no runtime
dependency on either tool.

## Pattern

1. Generate or score with promptfoo / DeepEval as usual.
2. Save each model response as a JSON file under `outputs/`.
3. Point a `case.yml` at those files and run `aiqg run`.

```
record (promptfoo / DeepEval / your app)
        │
        ▼
   outputs/*.json   +   source.txt   +   case.yml
        │
        ▼
     aiqg run          ← offline, exit 0/1/2
```

## From promptfoo

promptfoo writes results to a JSON/JSONL output when you ask it to. Dump the
response bodies into a case directory:

```bash
# after a promptfoo run that left results.jsonl with a "response" field
aiqg ingest results.jsonl --out my_case/outputs --jsonpath response
# write my_case/source.txt and my_case/case.yml, then:
aiqg run my_case
```

If promptfoo's export nests the model output differently, adjust `--jsonpath`
(dotted path) or write a three-line script that maps each row onto
`outputs/0001.json`. Keep promptfoo for prompt iteration and red-teaming;
keep aiqg as the merge-blocking gate on the files you commit.

## From DeepEval

DeepEval tests usually assert metric scores in pytest. To feed aiqg, persist
the same `actual_output` (or structured extraction) your metrics already see:

```python
# inside a DeepEval test, after you have the model response as a dict/string
from pathlib import Path
import json

out = Path("my_case/outputs")
out.mkdir(parents=True, exist_ok=True)
payload = actual_output if isinstance(actual_output, dict) else {"answer": actual_output}
(out / "0001.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

Then add `case.yml` with `required_fields`, `grounding`, `snapshot`, etc., and
run `aiqg run my_case` in CI. DeepEval keeps semantic metrics; aiqg keeps the
cheap, deterministic failures (broken JSON, missing fields, invented totals,
fallback phrases).

## What not to do

- Do not call promptfoo or DeepEval from inside aiqg. There is no plugin hook
  and no optional extra for them.
- Do not replace their LLM-judge scores with aiqg checks, or the reverse.
  Different jobs: score freshness vs gate recorded fixtures.
