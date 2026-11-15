# Research adequacy: claim-specific admission, not a universal guarantee

## Mandatory research rule

Before a **new model experiment is used to test a scientific claim**, its model
size, training duration, dataset and training regime must each have an explicit,
reviewed justification tied to that exact claim. Missing or inadequate support
blocks claim-bearing execution through the adequacy gate. A small diagnostic is
permitted only under its own bounded diagnostic claim, not as an exception that
silently inherits a broader conclusion.

A run completing, a parameter count matching, or a training loss falling does not
establish suitability. Old ungated runs are **UNASSESSED**, not grandfathered PASS.
No result from an unassessed setup may be promoted as adequate under this rule.

## Feature and integration

TrainLab v1/v2 recipes default to `execution_purpose: research`, including recipes
that omit the field. Research execution requires a pinned `research_adequacy`
contract with `file` and `sha256`, and a post-run `execution` reconciliation
contract. The contract file and all referenced source summaries must be declared
`inputs`. Missing contracts block before subprocess launch and retain UNKNOWN
refusals; UNKNOWN/INADEQUATE preflight evidence likewise blocks and is retained.

`run_experiment` enforces this in CLI/HTTP, Research Lab queue/replay, lifecycle
preflight, memory campaign and composed ecosystem paths that use the core runner.
Successful preflight is recorded as `PLAN_ADMITTED`, not executed adequacy. After
the command completes, a retained observation artifact must reconcile all four
dimensions with the frozen contract. Missing, mismatched or under-run evidence
fails the run even when the process exits zero. Success is recorded as
`EXECUTED_CRITERIA_MET`, with eligibility only `DECLARED_CONDITIONS_ONLY`, never
scientific qualification. `verify_run` rechecks the saved source bytes and
post-run receipt; `compare_runs` never infers scientific claim eligibility from
matching declarations.

Explicit `execution_purpose: engineering_diagnostic` or `historical_replay`
permits software acceptance/replay without a scientific adequacy contract. Those
runs remain UNASSESSED and claim eligibility NOT_ESTABLISHED. A supplied contract
is never ignored, even for an exempt purpose. These modes are not ways to qualify
model research: changing scope requires a research recipe and its evidence. See
[the migration inventory](research-adequacy-migration.md) for shipped examples.

Recipe identity is SHA256 of canonical finite JSON of the complete recipe excluding
only `research_adequacy` (use `recipe_identity`). Input closure includes every other
recipe input, not just favorable evidence files. The contract's own hash is supplied
by the recipe, avoiding a circular hash. Any budget, command, seed, dataset or other
recipe change requires a new contract and review. Frozen snapshots, not concurrently
mutable directories, remain required for execution; commands are trusted local code.

**Enforcement boundary:** all supported claim-bearing orchestration through the
core runner now fails closed by default; existing historical receipts retain
integrity verification but gain no adequacy. Explicit non-claim purposes preserve
software diagnostics. Trusted Python callbacks, low-level model APIs and external
scripts cannot be made incapable of arbitrary execution by a recipe validator;
their cost/observation reports do not establish research adequacy. This is not a
sandbox or an authenticated global policy, and a false purpose or fabricated
observations are not independently detected. No existing CSM, LRC or other
scientific campaign is automatically qualified or silently relabeled.

## Contract

`schema` is `trainlab.research-adequacy.v1`. Required fields:

- `claim`, `scope`, `excluded_claims`: exact question, supported population and limits.
- `claim_kind`: `bounded_diagnostic`, `fixed_budget_comparison`, `generalization`, or
  `capacity_limit`. A label does not certify that claim.
- `recipe_sha256`, `inputs`: exact recipe identity and other input name-to-SHA256 map.
- `review`: distinct declared `author` and `reviewer`, textual `basis`, and
  `criteria_frozen_before_evaluation: true`. These are operational assertions, not
  authenticated reviewer identities or proof of chronology.
- `dimensions`: exactly `model_size`, `training_duration`, `datasets`,
  `training_regime`. Each includes textual `configuration`, `justification`,
  `limitations`, and 1–32 criteria.

Each criterion has `id`, `rationale`, `evidence` (a pinned input filename), `field`
(top-level scalar key), `operator` (`ge`, `le`, `eq`) and a finite numeric
`threshold`. Missing observations are UNKNOWN; false comparisons are INADEQUATE.
Boolean and nonfinite observations are rejected. No executable evaluation
expressions or callbacks are accepted. Evidence files must be authorized,
public-safe, flat finite-scalar summary JSON. Do not supply private rows or labels.
The complete retained report is limited to 1 MiB before execution.
All source text is retained locally to permit byte-hash verification and replay;
the tool does not sanitize arbitrary sensitive data or authorize publication.

## What scientific review must establish

| Dimension | Required reasoning and evidence appropriate to the claim |
|---|---|
| Model size | Exact parameters, architecture/configuration, context and state capacity; primitive competence or other capacity control. Matching parameter counts alone is insufficient. |
| Training duration | Actual updates and token/example exposures, learning curves, stopping rule and budget rationale. A fixed-budget comparison need not converge, but cannot establish architectural incapacity. A capacity-limit claim needs convergence and capacity/budget sweeps or comparably discriminating evidence. |
| Datasets | Frozen Forge release/splits, semantic coverage, independent sampling groups, shortcuts/leakage checks, and task discrimination. Generalization requires genuinely held-out structure appropriate to the stated claim. More rows of familiar templates do not establish it. |
| Training regime | Optimizer, objective, supervision, curriculum, batching, source/runtime lock and meaningful comparator calibration. Equal information and training budget need evidence, not parameter-count inference. |

Set scientifically meaningful thresholds **before** looking at claim-evaluation
outcomes. Independent review must challenge their relevance, not merely their
presence. Use existing Forge audits, TrainLab training observers, competence panels,
comparison ledgers and crossed-uncertainty reports to produce the summary evidence.
Keep full provenance as declared inputs. Do not replace these tools with invented
numbers or interpret this checker as independently recomputing their observations.

For example, a COPY-through-alias transfer probe after training only direct COPY
can test that particular transfer. It cannot establish a general capacity limit,
and more training on the same direct-COPY examples does not repair the coverage
argument. Likewise a still-falling learning curve leaves convergence unestablished,
but does not invalidate an honestly scoped fixed-update comparison.

## Post-run reconciliation

For research, the contract additionally requires `execution`:

```json
{"execution": {"artifact": "executed-adequacy.json", "dimensions": {
  "model_size": [{"field": "parameters", "operator": "eq", "threshold": 18359, "rationale": "pinned candidate"}],
  "training_duration": [{"field": "committed_updates", "operator": "eq", "threshold": 768, "rationale": "declared comparison budget"}],
  "datasets": [{"field": "consumed_examples", "operator": "eq", "threshold": 24576, "rationale": "actual exposure requirement"}],
  "training_regime": [{"field": "optimizer_steps_with_declared_regime", "operator": "eq", "threshold": 768, "rationale": "regime must actually execute"}]
}}}
```

These are illustrative counters, not sufficient scientific criteria. Include every
relevant measured exposure, model/state limit, split identity and regime check for
the exact claim. The artifact must be among recipe `artifacts`. Its schema is
`trainlab.execution-adequacy-observations.v1` with `recipe_sha256`, full `inputs`
name/hash map, `producer: {file, sha256}` naming a separate declared source input,
and flat finite numeric `observations`. Every dimension requires 1–32 conditions.
Observation provenance is pinned, but truthful instrumentation remains unverified.
An exact recipe identity does not prove the program honored the recipe. Observer
and dataset validators should generate these observations; reviewers must inspect
that implementation. Training loss and parameter count alone cannot do so.

Failed or missing post-run observations leave claim eligibility NOT_ESTABLISHED;
no successful execution metric overrides them. The original observation artifact
and derived report are retained and checked on replay. Historical byte-integrity
verification remains distinct from eligibility for new scientific claims.

## Guaranteed behavior and limits

The executable guarantee is fail-closed enforcement of required research contracts,
identity and numeric necessary conditions before and after execution on supported
runner paths. Preflight **DECLARED_CRITERIA_MET** and final
**EXECUTED_CRITERIA_MET** never mean "scientifically adequate". It does
not prove that criteria are sufficient, evidence is truthful, or reviewers are
independent. Veritas scientific qualification remains `NOT_QUALIFIED`; existing
qualification/replay/contamination gates are not bypassed or replaced.

Inference and training costs remain separate. Under the user's 12:1 inference
priority, assess complete-call quality and cost on the **same** workload; the ratio
is not a license to combine unrelated accuracy/timing tables or ignore training
adequacy. No new threshold or weighted scalar is imposed by this feature.

## Verification

`PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests -p test_research_adequacy.py`

Constructed acceptance fixtures exercise admission and refusal, exact recipe/source
binding, durable UNKNOWN refusal, altered-report rejection, actual guarded command
execution, and independent saved-source verification. They are implementation
checks, not model training or validation of scientific criteria.

## Native paired-benchmark evidence

An optional `benchmark_projections` object maps a benchmark report input filename
onto its `panel` and `workbench` input filenames. All three must be distinct and
part of the recipe's pinned input closure. This explicitly opts into the native
`trainlab.benchmark-execution.v1` adapter; raw nested reports are otherwise rejected
as scalar summaries.

```json
{"benchmark_projections": {
  "benchmark.json": {"panel": "panel.json", "workbench": "report.json"}
}}
```

Criteria may refer to the benchmark filename and the adapter's scalar metrics.
The gate also adds a mandatory `native_benchmark_admissible` condition regardless
of which favorable metrics the author selected. The adapter validates identities,
observation closure and native statuses, recomputes reference findings from the
pinned panel and observed output hashes, and preserves failures or incomplete
execution. All original source bytes are retained and rechecked during receipt
verification, within the same aggregate size limit.

This addresses a concrete misleading-summary case: the public #567 examples pass
matched direct COPY but their references disagree on COPY through an alias. Both
panels can have identical aggregate changed/invariant group counts because other
rows already satisfy those counts. A COMPLETE Workbench run with OBSERVED coverage
can still contain a FAILED diagnostic. Neither execution completion nor favorable
group counts can erase a failed row through this adapter.

The adapter certifies neither independent callbacks nor truthful execution. It
checks recorded evidence consistency, not regenerated function execution. It does
not infer missing claim-relevant strata or independence from group names, and it
does not supply the other three adequacy dimensions. Review must explicitly demand
appropriate COPY/alias cases or other claim-specific coverage. Full qualification
and adequacy review of existing scientific campaigns remain separate; no missing
scientific evidence was fabricated during migration.
