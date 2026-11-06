# Verifier Qualification Suite

Verifier qualification evaluates the reward mechanism as an independently versioned artifact. A
task distribution is not verifier-valid merely because its reference solver receives a high score.

## Required falsifier taxonomy

Every qualified verifier fixture manifest contains at least one fixture for each of:

- correct solutions;
- alternative correct strategies;
- partially correct outputs;
- incorrect but plausible outputs;
- reward-hacking attempts;
- invalid state mutations;
- missing evidence;
- authority/process violations;
- forbidden side effects;
- nondeterministic perturbations;
- malformed artifacts;
- adversarial edge cases.

Fixtures declare expected pass behavior and an admissible reward interval. Correct and alternative
correct fixtures must be expected to pass. The suite evaluates semantics and reward bounds; it does
not compare an alternative strategy with a preferred reference trajectory.

Fixture manifests bind the environment digest, verifier digest, suite version, and exact fixture
contents. Every fixture requires replay evidence, and deterministic qualification requires at least
two replays per fixture. Replay evidence is content-addressed separately from the aggregate report.

## Measurements and gates

The report records these independent measurements:

- false-positive and false-negative rates;
- alternative-solution acceptance;
- reward-hack resistance;
- deterministic score/component reproduction;
- evidence dependence;
- state-grounding correctness;
- process-rule correctness;
- side-effect sensitivity;
- ambiguity sensitivity;
- aggregate expected pass/reward behavior.

Known reward-hack fixtures that pass or exceed their declared reward ceiling fail qualification.
Missing fixture categories, fixture replays, repeated replays, or category-specific observations are
`UNKNOWN`, not `PASS`. Any failed gate makes the report `FAIL`; otherwise any unknown gate makes the
report `UNKNOWN`; only an all-pass report is `PASS`/qualified.

## Maturity integration

`verifier_maturity_evidence` derives the three v1 maturity transition artifacts from a
content-addressed report:

- `verifier_qualification`;
- `falsifier_fixtures`;
- `reward_hack_resistance`.

An incomplete or failing verifier report therefore cannot promote an environment to
`VERIFIER_VALIDATED`.

## Scope

This suite defines the generic qualification protocol and evidence model. Every concrete Veritas
verifier still needs domain-specific falsifier fixtures and actual replay results. The existence of
the framework does not qualify existing verifiers retroactively.
