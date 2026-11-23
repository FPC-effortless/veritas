# Latent diagnostic implementation validation

Validation date: 2026-11-23. This record covers the implementation of the latent
atlas and research-cycle diagnostic methods, not a new model research campaign.
The executable method inventory is in [latent-research.md](latent-research.md).

The final numerical/native validation binds TrainLab source and atlas template
identity `c328b9bb44406949c349d539e459f12bc33b35556d2eb0d6686adaf2fe864900`.
It used Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, scikit-learn 1.8.0,
CPU PyTorch 2.10.0, Matplotlib 3.10.8 and ReportLab 4.4.9. BLAS and OpenMP
thread counts were bounded to one. Native source interfaces also used one CPU
thread. A changed implementation or runtime needs fresh replay evidence.

## Executed verification

| Check | Observed result | Scope |
| --- | --- | --- |
| New diagnostic suite, ordinary Python | 102 passed | Native, numerical, source, panel, serialization, report and gate falsifiers; optional archive fixtures available |
| Same suite under `python -O` | 102 passed | Runtime validation does not depend on Python assertions |
| Existing TrainLab suite | 363 passed, 7 optional checks skipped | 370 collected tests; existing runner and admission behavior |
| Existing Forge suite | 126 passed | Existing source/release integration |
| Existing Research Lab lightweight suite | 86 passed, 5 optional native checks skipped | 91 collected tests; no optional training rerun |
| Saved atlas geometry | 49 of 49 views matched | Compared with preserved outputs at the validator's declared numeric tolerance |
| Saved cycle006 position statistics | 1,188 estimates checked, zero mismatches | Point estimates and archived confidence interval draws |
| Actual native model workflows | 33 of 33 diagnostic jobs `TESTED` | Four source/checkpoint interfaces on constructed byte inputs |
| Actual native workflow offline replay | All four bundles byte-exact | 12 numerical jobs recomputed, 21 verified captures reused; zero model forwards or training updates during replay |
| Ruff | Passed | All new package modules, examples and tests |
| Plot exports and reports | Passed | Nine figure families; PNG/SVG/PDF outputs; source data; incomplete-figure handling |
| PDF visual inspection | Passed | Rendered native report coverage and figure pages inspected for clipping and layout |
| Atlas script | JavaScript syntax passed | Generated script parsed with Node; unsafe text escaped and row alignment checked |
| Browser interactions | Not executed locally | Local browser launch was blocked by the execution environment; an explicit Playwright CI check is supplied |

The original-checkpoint workflow contains native parity, bounded latency,
capture, token-row preparation, PCA, decoder replay, source-record folds and
cross-fitted head compression. CSM additionally exercises retrieval/state and
future-access controls. Exact native instrumentation/readout parity and the
later array replay are separate checks. Latency results do not establish a
quality-qualified architecture ranking.

The actual Forge → TrainLab → Research Lab example also produced a dataset
release, a supervised command execution receipt, an evidence ZIP and imported
research-memory records. Its observations are explicitly constructed. Installed
wheel/source-distribution acceptance is recorded separately for the delivered
build; these package checks do not promote scientific qualification.

## Defects found during independent review and corrected

The review produced executable adversarial checks, including:

- input/factory files changing between identity verification and use;
- implicit checkpoint dtype conversion and altered restored state tensors;
- native instrumentation disabling a Transformer fused execution path;
- literal metadata being mistaken for a required native capability;
- empty first-update captures and nonfinite scalar values falsely passing parity;
- a valid counterfactual pair replacing a declared full factorial panel;
- duplicated panel cells preserving row count while removing required conditions;
- mixed numeric/string identities silently combining records;
- failed nested diagnostic controls disappearing behind a successful outer status;
- failed figures and worker execution appearing complete;
- multi-array captures and downstream CKA changing order during saved-output replay;
- serialization-tag-shaped metadata being interpreted as an array or byte reference;
- an atlas export syntax error preventing interactive initialization.

All retained blocking findings were corrected and checked. Independent review of
the final exact commit remains a separate review record; this document does not
substitute for the repository's GitHub review provenance requirement.

## Reproduce

The install and ordinary test commands are in the main guide. With an explicitly
authorized local copy of the original study artifacts, run:

```bash
VERITAS_LATENT_ARCHIVE_ROOT=/path/to/archives \
  python -m unittest discover -s integrations/trainlab/tests_latent -v

python integrations/trainlab/examples/validate_latent_archive.py \
  --archive-root /path/to/archives --output /new/archive-validation.json

python integrations/trainlab/examples/validate_latent_native.py \
  --archive-root /path/to/archives --output /new/native-validation
```

No checkpoint, corpus, private research row, original source bundle or sealed
evaluation is distributed with this change. Runtime conformance on these four
interfaces does not establish support for every possible architecture. Other
implementations need explicit adapter capabilities and their own native parity
checks. Missing hooks remain unsupported, and scientific qualification remains
`NOT_QUALIFIED`.
