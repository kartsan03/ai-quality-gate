# Changelog

## 0.3.0 - 2026-09-02

### Added

- `--junit FILE` on `aiqg run` writes JUnit XML, so CI renders gate failures as annotated test results.
- `aiqg init DIR` scaffolds a working example case to edit into your own.
- Docs: [checks reference](docs/checks.md) and [recording outputs](docs/recording-outputs.md).
- CONTRIBUTING, issue/PR templates, code of conduct.

### Changed

- Malformed case files (missing required keys, unknown checks, `json_schema`/`snapshot` without a schema source, bare sections, invalid YAML) now fail with a clear setup error and exit `2` instead of a traceback.
- Output paths are printed with forward slashes on every platform.

## 0.2.0 - 2026-08-25

### Changed

- Setup errors (bad path, no cases, unknown check) exit `2`, keeping exit `1` unambiguous for gate failures.
- `--version` flag.

## 0.1.0 - 2026-07-15

### Added

- Initial release: seven deterministic checks, static HTML report, passing and regression example sets, CI workflow.
