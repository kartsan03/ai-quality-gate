# Recording outputs

aiqg never calls a model. The gate runs against recorded JSON outputs that you
commit next to the case. What a case needs:

```
my_case/
  case.yml          # the rules
  source.txt        # the text the outputs were generated from
  outputs/
    run_1.json      # one JSON file per recorded model output
```

Four ways to get there.

## From logs with `aiqg ingest`

If your pipeline logs JSONL (one JSON object per line), split them into
per-output files:

```
# whole object per line
aiqg ingest pipeline_logs.jsonl --out invoice_extraction/outputs

# keep only a nested field (dotted path)
aiqg ingest pipeline_logs.jsonl --out invoice_extraction/outputs --field response

# stdin
cat pipeline_logs.jsonl | aiqg ingest --out invoice_extraction/outputs --field response
```

Writes `0000.json`, `0001.json`, … into `--out` (default `outputs`). Empty
input or a missing `--field` is a setup error (exit 2).

## From logs (manual)

```python
import json
from pathlib import Path

out = Path("invoice_extraction/outputs")
out.mkdir(parents=True, exist_ok=True)
with open("pipeline_logs.jsonl", encoding="utf-8") as logs:
    for i, line in enumerate(logs):
        record = json.loads(line)
        if record["task"] == "invoice_extraction":
            (out / f"{i:04}.json").write_text(
                json.dumps(record["response"], indent=2), encoding="utf-8"
            )
```

## From a replay script

Keep a golden set of inputs, replay them against your pipeline, and dump the
responses. Re-run the replay whenever the prompt, model, or pipeline changes;
the gate then enforces the new outputs.

```python
import json
from pathlib import Path
import requests

out = Path("invoice_extraction/outputs")
out.mkdir(parents=True, exist_ok=True)
inputs = [json.loads(l) for l in open("golden_inputs.jsonl", encoding="utf-8")]
for i, item in enumerate(inputs):
    r = requests.post("http://localhost:8000/extract", json=item, timeout=60)
    (out / f"{i:04}.json").write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
```

## From integration tests

Wrap your client so every response is also written to `outputs/` during a
normal test run. The recorded files become the gate's fixtures.

## Multiple runs for stability

The `stability` check compares recorded runs of the same input. Record the same
input N times and save them as `run_1.json`, `run_2.json`, ... — files are
picked up by `outputs_glob` and compared in sorted order.

## Volatile fields

Timestamps, latencies, confidences and other values that legitimately change
between runs should be excluded from `snapshot` via `ignore`; that list drops
keys recursively before the diff.

## Updating snapshots

After a deliberate output change, rewrite the approved snapshot from the first
recorded output of each case:

```
aiqg snapshot --update path/to/cases
# or, update then re-run the gate in one step:
aiqg run path/to/cases --update-snapshots
```

Both refuse to run when `CI=true` or `GITHUB_ACTIONS=true`, so a misconfigured
workflow cannot silently rewrite golden files in CI.

## What to commit

Commit the source text, the case file, and the recorded outputs. The gate is
offline, so CI needs the files in the repo.

Treat recorded outputs like golden files: update them deliberately by
re-running the replay, and review the diff. A snapshot failure right after a
deliberate change means "approve and commit the new `expected.json`" — not
"ignore the gate".
