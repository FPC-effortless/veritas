# Repository-wide Python quality baseline

## Reproduction identity

The baseline uses Python 3.12 with Ruff 0.16.5 and Mypy 2.3.1, pinned in
`requirements-quality.txt`. Commands are recorded verbatim in
`python-quality-baseline.json` and executed by `tools/quality_baseline.py`.

| Revision | Role | Ruff diagnostics / files | Mypy errors / files |
| --- | --- | ---: | ---: |
| `df5d6f94d53ee15c988c282827b86dec039de8ef` | `main` when issue #103 was implemented | 1,107 / 198 | 168 / 44 |
| `5c56949f97c5c407aabac3f3abe9efc7affe50ed` | PR #99 convergence head and base for issues #100–#103 | 1,114 / 197 | 168 / 44 |
| issues #100–#103 candidate | committed ratchet baseline | 1,110 / 194 | 168 / 44 |

The issue description recorded an earlier unpinned diagnostic observation of 118 Ruff issues and
174 Mypy errors across 45 files. That result is not reproducible as a release gate because neither
the tool versions nor the exact command scope were recorded. It is retained as historical context,
not silently presented as equivalent to the pinned full-repository run above.

## Enforcement decision

The repository uses a full-repository ratcheted baseline. This is stronger than a changed-files-only
check because every run evaluates every Python source surface, while still allowing independent
component owners to remove existing debt without a repository-wide cleanup commit. A change fails
when it introduces a new diagnostic fingerprint or raises an existing fingerprint's count.

The current owner-lane and rule-code counts are stored in the baseline's `summary`. The largest
Ruff class is line length (`E501`); it should be handled mechanically and separately from type-model
work. The largest Mypy class is argument incompatibility (`arg-type`); each package lane must review
those as API/type-contract defects rather than suppressing them globally.

This baseline is implementation-quality evidence only. It does not alter functional, scientific,
frontier, sealed-portability, or release qualification status.
