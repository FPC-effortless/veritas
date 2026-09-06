# Zero-Capital Frontier Execution Plan

Status: active operating constraint as of 2026-08-27.

## Objective

Veritas is being developed under a hard **$0 personal-spend constraint** until external capital, credits, or partner-supplied compute is available.

This changes experiment ordering, not scientific standards. Frontier Qualification thresholds are not relaxed to fit free resources. Evidence that cannot be obtained without unacceptable cost or private-data disclosure remains `UNKNOWN`, and the final state remains `NOT_YET_FRONTIER_QUALIFIED` until the required evidence exists.

The near-term objective is:

> Produce the strongest reproducible, buyer-safe evidence package available at zero personal cost, and turn genuinely capital-dependent measurements into explicit funding milestones.

## Non-negotiable rules

1. **No personal expenditure.** Use existing hardware, public-repository CI, free compute allocations, research/startup credits, grants, or partner-supplied compute.
2. **No threshold shopping.** Frontier policy is fixed before results are inspected. A failed gate is a result, not a reason to loosen the gate.
3. **No fake sample-size growth.** Re-running the same deterministic 30 private SRE cases does not create new independent observations.
4. **No private-benchmark leakage for free access.** The sealed SRE panel must not be submitted to a consumer/free provider tier whose terms allow prompt/content use for product improvement or training.
5. **External private-data egress is opt-in.** `frontier_run_sre_calibration.py` refuses a non-local endpoint unless `--allow-external-private-data` is supplied deliberately after the operator verifies the relevant provider/account data-use terms.
6. **No frontier-by-name inference.** Model tier is explicitly predeclared. Parameter count, branding, benchmark reputation, or a good observed score never silently upgrades a model to `strong` or `frontier`.
7. **Buyer-safe public outputs only.** Per-case private predictions, scenario identifiers, labels, source material, and hidden oracle content stay evaluator-side.

## SRE v4 preservation and recovery state

The encrypted SRE v4 private seal from GitHub Actions artifact `9634991904` was copied to durable private storage before its scheduled Actions expiration.

Preservation checksum:

`sha256:9dcfde1f915d51f6f8cec954bf6ed651391dc6f71a24b143273eb1168b57f4aa`

The matching RSA private key has now been recovered from private storage and cryptographically verified against the committed SRE v4 public sealing key. The preserved seal was decrypted evaluator-side using the original RSA-OAEP-SHA256 and AES-256-CBC/PBKDF2-200000 procedure. Both encrypted-file checksums and the recovered ZIP integrity check passed.

The recovered frozen identities match the public SRE v4 record exactly:

- candidate `SRE-CAND-92A84929AD1E82E24357`;
- qualification report `QREPORT-C585121E94D91766BB6664E3`;
- panel `QPANEL-AFF065BA4C2FD75BE9BB3EBE`;
- evidence manifest `EVID-2C69B48DCDD5F2232EABDC9B`;
- private release manifest `PRIVREL-036192DA63716D331C929C0C`;
- 87 scenarios, including 30 private-test cases;
- 16 source files.

The private key, decrypted bundle, per-case labels, scenario identifiers, source material, and hidden oracle content remain outside the repository and public CI artifacts.

## Experiment order under $0

### Z0 — preserve and recover the evaluator asset — COMPLETE

- Encrypted seal preserved in durable private storage.
- Matching private key recovered and cryptographically verified.
- Original encrypted checksums verified.
- Frozen private bundle decrypted and ZIP integrity verified.
- Decrypted evaluator material retained outside the repository/public CI.

### Z1 — zero-inference evidence — ACTIVE

Privately derive and publish only aggregate Frontier artifacts for task/source diversity, duplicate concentration, grammar/component/schema/topology concentration, failure-category breadth, split diagnostics, and immutable artifact identities.

The first evaluator-side pass confirms meaningful source, causal-class, and semantic-cluster breadth, but SRE v4 lacks enough explicit structural dimensions for a default Frontier task-diversity PASS. Frontier Qualification therefore requires at least four available core diversity dimensions; sparse coverage remains `UNKNOWN` rather than silently passing on the available metrics.

A diversity failure or `UNKNOWN` is not repaired by changing thresholds. It becomes evidence for a richer successor environment such as SRE v5.

### Z2 — zero-cost open-weight calibration ladder

Use private/local execution. A practical venue is a private Kaggle notebook/dataset or another free compute allocation where the operator accepts the platform's storage/processing terms. Private material must never be placed in a public dataset or notebook.

Cycle-1 tier assignments are separately preregistered in `model-tier-preregistration.md`. The exact immutable model revision SHA must be captured in `model_snapshot` before each score is inspected.

The first zero-cost pass intentionally declares no model `frontier`. A strong open-weight result can satisfy gates whose policy admits the `strong` tier, but it is not evidence that independent frontier-lab models have been tested.

### Z3 — paired capability separation on the existing 30 cases

When weak and strong systems run on the same private cases, reduce private rows to the buyer-safe 2×2 aggregate:

- `both_correct`
- `weak_only_correct`
- `strong_only_correct`
- `both_wrong`

Frontier Qualification uses these paired outcomes preferentially for capability separation. This exploits same-case information without publishing case identities and without pretending repeated runs create a larger panel.

### Z4 — harness sensitivity for free

Run the same strong model snapshot against the same frozen panel under at least two controlled harnesses:

1. `direct-json` — current one-shot classification contract;
2. `evidence-two-stage` — evidence normalization followed by causal classification.

The model snapshot and panel stay fixed. Only the harness changes. If the measured effect is below policy threshold, the harness gate fails rather than being forced to pass.

### Z5 — actual generalization measurements

Measure required modes explicitly rather than inferring performance from split labels. The default policy requires random held-out and source-disjoint performance. Grammar-, component-, and compositional-OOD transfer remain separately representable.

### Z6 — training value and regression control last

Training is deferred until calibration shows useful signal. Use the strongest trainable model that fits free compute, LoRA/QLoRA where appropriate, and evaluate pre/post on permitted held-out SRE transfer, source-disjoint transfer, and a frozen unrelated control benchmark.

Existing Training Value v3 remains within-family evidence only. It must not be promoted to cross-family or external-benchmark transfer.

## Free-resource policy

### Public GitHub Actions

Use public-repository Actions only for code tests, deterministic fixture reports, schema validation, and buyer-safe aggregate artifacts. Never upload the decrypted SRE private bundle or per-case private reports to a public Actions artifact.

### Kaggle / other free hosted compute

Use private notebooks and private data containers only. Prefer a setup where model weights are obtained before private evaluation and network access can then be disabled. Free hosted compute is a third-party processing environment, not a proof of absolute confidentiality.

### Free closed-model APIs

Do not send the sealed private benchmark merely because an API is free. Free tiers may have data-use terms unsuitable for a valuable private evaluator. Closed-model evaluation can be performed later with appropriate contractual/API protections, donated credits, buyer-run evaluation, or a partner that supplies the model endpoint without acquiring the benchmark corpus.

### Credits and partner compute

Compute/model credits, research access, evaluator partnerships, and buyer-supplied inference count as zero-personal-spend resources. Pursue them in parallel with cash fundraising.

## Fundraising evidence package

The raise should distinguish **already built**, **demonstrated at $0**, and **capital-unlocked** work.

### Already built

- scientifically qualified SRE v4 release;
- frozen benchmark/evidence identities;
- recovered private evaluator asset with verified key custody;
- independent Frontier Qualification layer;
- deterministic task-diversity analysis;
- strong/weak calibration contracts;
- buyer-safe reporting;
- Training Value and commercial evaluation infrastructure.

### Demonstrate at $0

- open-weight capability ladder;
- non-saturation result for a predeclared strong tier;
- paired capability-separation evidence;
- failure-mode breadth;
- buyer-safe diversity diagnostics with explicit structural-coverage limits;
- controlled harness sensitivity;
- small/medium-model training transfer and regression control where free compute permits.

### Capital / credits unlock

- independent evaluations across multiple frontier labs/providers;
- stronger post-training experiments;
- larger and more diverse environment generation;
- hosted/private evaluator operations;
- customer pilots and secure buyer-side deployments;
- richer CompanyWorld long-horizon calibration.

The fundraising claim is therefore not "fund us so we can find out whether anything works." It is:

> Veritas already has qualified infrastructure, a recovered frozen private evaluator, and zero-cost evidence; funding purchases the expensive validation, scale, and distribution steps that cannot be fabricated under a no-capital constraint.

## Exit criterion

Do not spend personal funds to force completion of Frontier Qualification. Exit the zero-capital phase only when cash funding closes, model/compute credits are awarded, a research/customer partner supplies protected compute, or a buyer runs the private evaluator in its own protected environment.

Until then, capital-dependent gates remain explicit `UNKNOWN` rather than becoming weaker claims.
