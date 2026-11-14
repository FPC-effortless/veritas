# Lifecycle preflight before model dispatch

ECOSYSTEM-ADMISSION-003 (#515) turns the bounded
[observability diagnostic](lifecycle-observability.md) into a guarded
TrainLab entry point. It addresses a concrete failure: a DELETE/recreate panel
can have no scored consequence of the absence interval. A completed diagnostic
command or a cached PASS must not authorize training on such a panel.

## Contract and boundaries

`research_lab.lifecycle_preflight` freezes a Forge release, pair inventory,
design, TrainLab recipe, all declared recipe inputs and installed ecosystem source
digests. The operator retains the returned protocol SHA256 outside that directory.
Every TRAIN and validation row must be available at the cutoff and belong to
exactly one controlled COPY/LINK pair. A pair must stay within one split and one
declared Forge subject. Targets, omissions, duplicate rows, changed focal bindings,
unsupported operations and malformed pairs are rejected.

For each split and each overwrite/delete-recreate stratum it counts pairs and
distinct declared Forge subjects separately. For deletion it additionally counts
subjects with changed composed answers and directly preserved absence witnesses
at composed queries. Empty overwrite interventions never count as deletion
coverage. Joint deletion ablations use the existing diagnostic's bounded semantics.
The minimum is at least 30 groups per split/stratum, including 30 sensitive and
30 preserved-absence groups in each deletion split. The floor can be raised but
cannot be lowered through this entry point.

These are **necessary mechanical conditions**, not a causal-template quotient or
power analysis. Forge subjects are declared groups, not independently proven
mechanisms. The research owner must supply and independently review causal
grouping, counterfactual oracle parity, shortcut controls, supervision, budgets
and supported model semantics. The software positive controls deliberately reuse
invented mechanisms under distinct subjects; they test this trust boundary and
must never be cited as scientific diversity evidence.

## Prepare and inspect

Install the four sibling ecosystem packages. Place the recipe at the source root.
Its `inputs` must include the pair inventory, design, model/runner dependencies,
and all four Forge files. Its `split_identity` must match the pinned manifest and
its `source_kind` must be CONSTRUCTED. A minimal source specification is:

```json
{
  "schema": "veritas.lifecycle-preflight.v1",
  "dataset": "dataset",
  "manifest_sha256": "EXTERNAL_FORGE_MANIFEST_SHA256",
  "cutoff": "2026-11-13T00:00:00Z",
  "pairs": "pairs.json",
  "recipe": "recipe.json",
  "design": "design.md",
  "minimum_groups": 30
}
```

`pairs.json` is a list of `{"records":["left-id","right-id"],
"stratum":"delete_recreate"}` objects; the other allowed stratum is `overwrite`.
Include exactly the selected TRAIN/validation inventory, never TEST IDs. The gate
does not export or score TEST. The standard Forge reader still internally verifies
the entire release's bytes, canonical rows and group assignments.

```bash
python -m research_lab.lifecycle_preflight prepare source/spec.json campaign
python -m research_lab.lifecycle_preflight record campaign --protocol-sha256 PIN
python -m research_lab.lifecycle_preflight verify campaign --protocol-sha256 PIN
```

`record` retains immutable aggregate reports and a Research Lab finding linked to
the Forge identity, including BLOCKED outcomes. `verify` recomputes without graph
writes or recipe execution. The CLI returns both the report and its canonical
`report_sha256`; a blocked report exits 1. Invalid or changed evidence exits 2.
Raw record IDs, keys, values and witness paths are excluded from the report.
The campaign directory and its data remain operator-private (created mode 0700).

## Review and dispatch

READY_FOR_REVIEW is the strongest automatic preflight result. A separate reviewer
must examine the frozen design, data, grouping and intended recipe, then provide:

```json
{
  "schema": "veritas.lifecycle-preflight-review.v1",
  "protocol_sha256": "PIN",
  "report_sha256": "CANONICAL_REPORT_SHA256",
  "verdict": "clean",
  "findings": [],
  "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
  "reviewer": "reviewer-session-id",
  "summary": "Exact scope, evidence reviewed, limits and execution decision."
}
```

Retain the SHA256 of that exact review file separately. Dispatch recomputes the
preflight and checks both pins before reserving an attempt:

```bash
python -m research_lab.lifecycle_preflight dispatch campaign --protocol-sha256 PIN --review review.json --review-sha256 REVIEW_FILE_SHA256
```

A missing/stale/blocking review cannot dispatch. A clean review cannot override
BLOCKED coverage. The review's identity and independence are operator assertions,
not authenticated remote identity or scientific qualification. Actual execution
also requires the operator's authority and budget; the JSON does not grant either.

One atomic execution-directory reservation prevents concurrent calls, failed
commands or interrupted controllers from silently launching another attempt. A
crash immediately after reservation may leave zero processes but still consumes
the attempt. Preserve it and create a separately reviewed new campaign when a
retry is justified. TrainLab owns process timeout, logs, terminal receipt and
artifacts; the research graph links the receipt to the review and preflight.

This is an entry-point guard for trusted local code. Existing direct TrainLab
calls and arbitrary host commands do not automatically route through it. It is
not a sandbox, enforcement against a malicious account, a whole-OS attestation,
or a claim that all research lanes have migrated. Broader rollout must select
this entry point explicitly. Scientific and frontier qualification remain
unestablished even after a successful command.

## Retrospective refusal exercised on 14 November 2026

The unchanged MEMORY-FAMILIES-046 release was checked through this entry point.
All 69 files in its recovered evidence archive verified. The original Forge
manifest remained `623c42b4c340b0861f5edf762c6cb19d5d3b1235a87b5ac5f1babbaf95b56b08`;
no data generation, regrouping, split-salt change or TEST selection occurred.

| Deletion split | Pairs | Declared groups | Sensitive pairs | Sensitive groups |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 378 | 18 | 28 | 1 |
| Validation | 21 | 3 | 0 | 0 |

Directly preserved-absence counts were identical to the sensitivity counts.
Overwrite groups were 19 in TRAIN and 2 in validation, also below the unchanged
30-group floor. The resulting report was BLOCKED with eight explicit coverage
reasons. A guarded dispatch refusal check observed zero TrainLab invocations and
no execution reservation; independent report reverification matched. No model fit
or scientific admission occurred.

Preflight protocol pin:
`0d1c90e0ecdaf0e278961191793de78ce05fab02d44b6fc7e144e00cfd21ed2a`.
Canonical report pin:
`0f2f2d8dc869a776d3120d3d7e1cad533c4d9624c6ac881bece888499eef05fb`.
Raw inputs and diagnostics remain in the authorized private evidence bundle.
