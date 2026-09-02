# Contributing

## Setup

```
git clone https://github.com/kartsan03/ai-quality-gate
cd ai-quality-gate
pip install -e .[dev]
pytest
python -m aiqg run examples/passing/
python -m aiqg run examples/regressions/   # exits 1 on purpose
```

## Ground rules

- Deterministic only: no model calls, no network, no embeddings, no scores.
- No new runtime dependencies without a strong reason.
- Failure messages must be human-readable: a failing check tells you exactly what broke.
- Exit code discipline: `1` = gate failure, `2` = setup error.

## Adding a check

1. Implement it in `aiqg/checks.py`. Per-output checks take
   `(config, output, source)` and return a list of failure strings (empty =
   pass); case-level checks like `stability` take `(config, outputs)`.
2. Register it in `aiqg/runner.py`.
3. Add tests in `tests/`.
4. Add an example to `examples/passing/` and a deliberately broken one to
   `examples/regressions/`.
5. Add a section to `docs/checks.md` and a row to the README check table.

## Pull requests

Keep them small. CI runs pytest plus both example sets — the regression set
must keep failing, that is the point of the project.
