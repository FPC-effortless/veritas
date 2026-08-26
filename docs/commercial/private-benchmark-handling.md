# Private Benchmark Handling

## Purpose

Veritas private-test value depends on keeping evaluator-only information out of the evaluated system and out of public release artifacts. In SRE, the underlying incident histories may originate from public sources, but the frozen split, later resolution notes selected as evaluator truth, causal labels and per-scenario oracle outputs function as private benchmark material once a release panel is defined.

## Information classes

### Public

May be published:

- benchmark family and version;
- candidate ID;
- panel ID;
- evidence-manifest ID;
- provider/source-family names;
- aggregate scenario counts;
- aggregate policy means;
- qualification gate results;
- aggregate customer/model scores and uncertainty;
- public prompt/output schema.

### Private evaluator material

Must not be committed to the public repository or uploaded as a long-lived public-repository artifact:

- frozen raw benchmark snapshots containing later resolution evidence;
- private causal labels;
- per-scenario oracle predictions;
- private split manifests when they make labels or source assignments recoverable;
- unreleased adversarial cases;
- customer trajectories where a contract treats them as confidential.

## Storage contract

A releaseable private suite must have:

1. a content-addressed evidence-manifest ID;
2. a private storage location outside the public repository;
3. access limited to evaluator operators and explicitly authorized customer personnel;
4. a recorded benchmark version, candidate ID and panel ID;
5. a recovery copy or documented regeneration procedure;
6. a retirement state if private truth is disclosed.

The current SRE v3 frozen suite has been copied to a private connected Drive location. Future commercial releases should use a dedicated private object store or equivalent controlled repository before scaling beyond design-partner pilots.

## CI / Actions rule

Qualification workflows may use raw private material transiently on an ephemeral runner. Persisted public artifacts must be sanitized and must not contain raw snapshots, per-scenario policy outcomes or private labels.

Short-lived internal workflow artifacts may be used only when required to transfer a frozen panel between jobs in one evidence run and should use the minimum feasible retention period.

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
5. return aggregate results;
6. disclose case-level diagnostics only under an agreed retirement policy.

If the customer cannot transmit inputs or outputs off-premises, move the evaluator into the customer-controlled environment while preserving the same oracle separation.

## Incident response

If private material is accidentally published:

1. remove or expire the public artifact where possible;
2. record the affected candidate/panel IDs;
3. treat the affected panel as potentially contaminated for future external claims;
4. rotate to a newly qualified private panel for new customers;
5. retain the old panel only for historical or internal regression analysis with the exposure disclosed.
