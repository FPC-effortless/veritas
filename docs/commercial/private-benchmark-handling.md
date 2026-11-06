# Private Benchmark Handling

## Purpose

Veritas private-test value depends on keeping evaluator-only information out of the evaluated system and out of public release artifacts. In SRE, the underlying incident histories may originate from public sources, but the frozen split, selected later causal evidence, causal labels and per-scenario oracle outputs become private benchmark material once a release panel is defined.

## Information classes

### Public

May be published:

- benchmark family and version;
- candidate ID;
- panel ID;
- evidence-manifest ID;
- qualification-report ID;
- private-release-manifest ID;
- provider/source-family names;
- aggregate scenario and stratum counts;
- aggregate policy means;
- qualification gate results;
- immutable private-bundle checksum;
- aggregate customer/model scores and uncertainty;
- aggregate confusion/per-class metrics;
- public prompt/output schema.

### Private evaluator material

Must not be committed to the public repository or persisted in readable form as a public-repository Actions artifact:

- frozen raw benchmark snapshots containing evaluator-only later evidence;
- private causal labels;
- per-scenario oracle predictions;
- per-case model predictions paired with expected labels;
- private split manifests when they make labels/source assignments recoverable;
- unreleased adversarial cases;
- customer trajectories where a contract treats them as confidential.

## Storage contract

A releaseable private suite must have:

1. content-addressed evidence-manifest, qualification-report, panel and private-release-manifest identities;
2. a private storage location outside the public repository;
3. access limited to evaluator operators and explicitly authorized customer personnel;
4. a recorded benchmark version and candidate ID;
5. a SHA-256-pinned evaluation bundle or equivalent immutable object version;
6. a recovery copy or documented recovery procedure;
7. a retirement state if private truth is disclosed.

SRE v3 is **retired/consumed** for external private-test claims because historical public Actions artifacts exposed its qualification material. Copying the same suite into private storage does not restore secrecy.

SRE v4 is **qualified and frozen**. Its source snapshots, exact split and evaluator-only causal evidence are retained in controlled private storage; its release identities and private-bundle checksum are pinned publicly.

## CI / Actions rule

Once a private benchmark release is frozen, public qualification CI must not reacquire mutable source feeds or regenerate/re-split the benchmark. It verifies the immutable release record instead.

Readable private benchmark material must not be transferred between public-repository workflow jobs using Actions artifacts. The commercial real-model workflow consumes a checksum-pinned private bundle directly from controlled storage into one ephemeral runner. Detailed operator reports remain in runner-temporary storage. Only sanitized aggregate outputs may be uploaded.

## Public model-report contract

A public/buyer-safe model report may contain aggregate metrics, class distributions, aggregate confusion counts and the sealed release identities, but must state and enforce:

- no private scenario identifiers;
- no per-case predictions;
- no per-case expected labels.

Balanced accuracy and macro F1 are primary metrics for multiclass SRE evaluation; raw accuracy must be reported beside the majority-class baseline.

## Disclosure and retirement

A benchmark case is **consumed** when its private expected answer, decisive later evidence, or oracle trajectory is disclosed to the evaluated model developer in a way that could influence a future attempt.

Consumed cases must not be presented as unseen private-test cases in future commercial evaluations. They may move to:

- development/debugging;
- training;
- public examples;
- regression diagnostics where prior exposure is explicitly disclosed.

A new private panel must be qualified before replacing consumed cases in a procurement-grade evaluation.

## Customer execution

Preferred order of operations:

1. keep the private suite evaluator-side;
2. send only the public prompt/evidence to the customer's model endpoint;
3. receive the model output;
4. score locally against private truth;
5. persist only the private operator record in controlled storage;
6. return a sanitized aggregate report;
7. disclose case-level diagnostics only under an agreed retirement policy.

If the customer cannot transmit inputs or outputs off-premises, move the evaluator into the customer-controlled environment while preserving the same oracle separation.

## Incident response

If private material is accidentally published:

1. remove or expire the public artifact where possible;
2. record the affected candidate/panel IDs;
3. mark the affected panel consumed for future external unseen-test claims;
4. rotate to a newly qualified private panel for new customers;
5. retain the old panel only for historical or internal regression analysis with the exposure disclosed.
