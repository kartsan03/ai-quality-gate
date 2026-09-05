# Checks reference

Every check is deterministic: same inputs, same verdict, no model calls. This
page documents every check and every `case.yml` key.

## Case file anatomy

A case is a directory containing a `case.yml`, a source text file, and recorded
JSON outputs.

```yaml
name: invoice_extraction      # required; shown in reports
task_type: extraction         # optional free-form label
source_file: invoice.txt      # required; path relative to the case directory
outputs_glob: outputs/*.json  # required; glob relative to the case directory
checks:                       # required; one or more of the checks below
  ...
```

Missing required keys, unknown check names, a `json_schema` or `snapshot`
section without a schema source, and invalid YAML are setup errors: `aiqg`
prints a message and exits `2`.

## json_schema

Validates each output against a JSON Schema (Draft 2020-12).

```yaml
json_schema:
  schema_file: schema.json    # path relative to the case directory
  # or inline:
  # schema: {type: object, required: [total]}
```

Failure message:

```
schema: $.total: '5' is not of type 'number'
```

## required_fields

```yaml
required_fields:
  fields: [customer.name, total]   # dotted paths into the output
```

Fails when a value is missing, an empty string, or an empty list. `0` and
`false` count as present.

```
required field missing or empty: total
```

## regex

```yaml
regex:
  fields:
    invoice_number: "^INV-\\d{4}-\\d{4}$"   # re.search semantics
```

A missing field fails; so does a present value that does not match.

```
regex: invoice_number='INV-1187' does not match '^INV-\\d{4}-\\d{4}$'
```

## grounding

Three independent options, combinable:

```yaml
grounding:
  fields: [vendor, total]       # each value must appear in the source text
  numbers_in: [answer]          # every number in the field must appear in the source
  require_citations: citations  # the field must be a non-empty list
```

Matching is substring containment after light normalization: lowercased,
whitespace collapsed, `$`, `,`, `€` separators stripped. `5,868.50` matches a
source that says `5868.50`. This catches copied-vs-invented values and numbers,
not paraphrase — see Limitations in the README.

```
grounding: total='6,868.50' not found in source
grounding: number '30' in answer not found in source
grounding: no citations in citations
```

Numbers are extracted with `\d[\d,.]*\d|\d`.

## forbidden_phrases

```yaml
forbidden_phrases: {}           # {} uses the built-in list below
forbidden_phrases:
  phrases: ["i cannot help with that"]
```

Case-insensitive substring search across every string value in the output,
recursing through nested objects and lists.

Built-in list:

- `as an ai language model`
- `as a language model`
- `as an ai assistant`
- `i don't have enough information`
- `i do not have enough information`
- `i cannot assist with`

```
forbidden phrase 'as an ai language model' in output
```

## snapshot

Compares each output to an approved JSON snapshot. `ignore` drops keys
recursively before the diff — for volatile values like timestamps, confidence,
or latency.

```yaml
snapshot:
  file: expected.json           # path relative to the case directory
  ignore: [confidence, extracted_at]
```

Structural equality, no fuzzy matching. Failures show a full diff:

```
snapshot: line_items.1.total: expected '100', got '140'
snapshot: vendor: unexpected value 'Nordwind Logistics GmbH'
```

## stability

Runs once per case, not per output: every recorded output must agree on each
listed field. To use it, record the same input several times (`run_1.json`,
`run_2.json`, ...); the gate matches `outputs_glob` and sorts by filename.

```yaml
stability:
  fields: [category, total]
```

```
stability: category differs across outputs: run_1.json='account_access', run_3.json='billing'
```

## Malformed JSON

An output file that is not valid JSON is reported as a `json_parse` failure for
that file. The run continues; the gate exits `1`.

## Dotted paths

All field lookups accept dotted paths (`customer.name`). List indexing
(`items.0.name`) is not supported.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All checks passed |
| `1` | At least one check failed — a gate failure |
| `2` | Setup error: bad path, no cases, malformed case file |


## Case file schema

In addition to the checks above, each `case.yml` is validated against the
packaged JSON Schema at `aiqg/case_schema.json` (required keys, known check
names, and basic shapes). Schema failures are setup errors (exit `2`) with an
`invalid case.yml` message.
