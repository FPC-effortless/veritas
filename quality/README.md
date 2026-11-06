# Python quality baseline and staged enforcement

Veritas pins Ruff and Mypy in `requirements-quality.txt` and enforces a repository-wide,
fail-closed ratchet with `tools/quality_baseline.py`.

## Policy

The committed `python-quality-baseline.json` is an allowlist of existing diagnostic fingerprints,
not a declaration that those diagnostics are acceptable forever. CI fails when Ruff or Mypy emits
any new `(tool, repository path, code, message)` fingerprint or increases its multiplicity. Removing
diagnostics is allowed, so ordinary subsystem work can ratchet the baseline downward. Tool crashes,
unparseable output, missing baselines, schema mismatches and version drift fail closed.

Fingerprints deliberately omit line numbers. Moving otherwise unchanged code does not create false
debt, while a changed error message, code, file, or duplicate count remains detectable. The baseline
stores no source lines or evaluator data.

## Ownership and cleanup stages

`diagnostics_by_owner_lane` assigns source debt to the first package below
`src/investigation_world/` (for example `portable_runtime`, `foundry`, or `observatory`). Repository
areas outside the package are assigned to their top-level directory. These component names are the
review ownership lanes until individual CODEOWNERS are adopted.

1. The repository-wide ratchet is required now and prevents net-new diagnostic fingerprints.
2. Mechanical Ruff cleanup should be submitted in component-scoped changes and must not include
   behavioral rewrites.
3. Mypy cleanup should be split by owner lane and fix the underlying type contract; blanket ignores
   and broad `Any` conversions do not count as cleanup.
4. A lane may switch to zero-tolerance enforcement when its baseline reaches zero. Full-repository
   zero tolerance is the final state, not a claim made by this baseline.

## Reproduce or update

```bash
python -m pip install -e .
python -m pip install -r requirements-quality.txt
python tools/quality_baseline.py check
```

After a reviewed cleanup, update the ratchet and inspect the diff before committing it:

```bash
python tools/quality_baseline.py update
git diff -- quality/python-quality-baseline.json
```

Do not update the baseline to admit new debt in the same change that introduced it.
