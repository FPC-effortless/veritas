# Capability Qualification Pilot — Scope Contract

This document defines the default fixed-scope Veritas qualification engagement. Commercial/legal terms may be attached separately; this contract defines the technical and evidence scope.

## Objective

Evaluate one consequential operational capability of one or more pinned agent configurations and produce a buyer-safe decision report grounded in executable state and independent verification.

The pilot is successful when it resolves the agreed decision with credible evidence. A low score, negative finding, or deployment recommendation of `DO_NOT_DEPLOY` is a valid result.

## Required inputs

Before execution, freeze:

- completed Capability Intake Contract;
- exact model/agent/harness/runtime identities;
- target capability and decision;
- primary deployment threshold;
- hard invariants and unsafe outcomes;
- tool and permission envelope;
- private/public data boundary;
- evaluation distribution/version;
- verifier/version;
- repeated-run policy;
- case disclosure/retirement policy;
- comparison conditions, if more than one system is evaluated.

## Default work packages

### A. Integration and dry run

- connect the model, endpoint, harness, container, or checkpoint through an agreed adapter;
- verify tool/action schemas and structured outputs;
- verify private evaluator state is inaccessible to the evaluated agent;
- run non-private/synthetic smoke cases;
- confirm trace, usage, termination, and verifier evidence are captured;
- fail closed on incompatible semantics rather than silently degrading the environment.

### B. Private qualification run

Run the frozen panel without changing task/verifier semantics after observing model behavior.

At minimum retain:

- exact model and harness identity;
- environment/task distribution identity;
- verifier identity;
- run/replicate identity;
- verifier-backed result dimensions;
- hard-invariant results;
- actual harmful side effects separately from blocked unsafe attempts;
- recovery outcome where applicable;
- usage/cost evidence when actually observed;
- buyer-safe aggregate failure categories.

### C. Failure analysis

Classify failures only to the resolution supported by evidence. Candidate categories include outcome, state, constraints/authority, side effects, process, evidence, efficiency, recovery, harness/tool, and unknown.

Do not infer model blame merely from low reward. Do not expose private case truth in the buyer-safe report unless disclosure is explicitly authorized and the affected cases are retired from unseen use where policy requires.

### D. Decision readout

Deliver a report using `decision-report-template.md` that states:

- whether the system met the predeclared threshold;
- uncertainty/reliability where material;
- dominant failure mechanisms;
- unsafe versus inefficient failures;
- deployment/authority recommendation;
- comparison between evaluated configurations, if applicable;
- known limitations and UNKNOWN gates;
- recommended next intervention or experiment.

## Optional extension: Capability Improvement Cycle

After the baseline report, the customer may make one declared intervention, such as changing the model, harness, prompt, tool interface, permissions, workflow, or training procedure.

The extension must freeze:

- intervention identity;
- what is allowed to change;
- what must remain fixed;
- held-out reevaluation panel/policy;
- regression panel;
- comparison metric and threshold.

The follow-up report may state that the intervention improved held-out capability if the comparison supports it. It must not attribute causality to Veritas-generated experience or claim training validation unless the relevant qualification policy is satisfied.

## Optional extension: Verified Training-Value Program

This extension is available only when the environment and experimental protocol satisfy the canonical training-value qualification requirements.

Required controls include, as applicable:

- train/held-out separation;
- baseline-before and heldout-before evaluation;
- exact training-bundle and method identity;
- baseline-after and heldout-after evaluation using the same verifier semantics;
- multi-seed/replicate evidence where required;
- exploit/reward-hacking monitoring;
- structural/OOD transfer classification;
- unrelated-capability regression checks.

Training loss, train-set reward, or one favorable seed is not sufficient evidence.

## Optional extension: Learning-Efficiency Program

This extension requires canonical resource-accounting evidence and an appropriate matched-budget control.

The treatment and control must disclose observed resource use, including available evidence for:

- examples/tokens;
- compute;
- teacher calls/tokens;
- human review;
- monetary cost;
- candidate-generation/selection overhead.

The primary outcome is verified held-out capability gain under matched resource budgets. Missing denominators remain UNKNOWN.

## Deliverables

Default deliverables are:

1. frozen capability/evaluation manifest or equivalent identity record;
2. buyer-safe capability scorecard;
3. reliability and hard-invariant summary;
4. failure-analysis summary;
5. representative buyer-safe traces or trace summaries where permitted;
6. deployment/authority recommendation;
7. evidence/maturity status and limitations;
8. recommended next experiment;
9. rerunnable regression identity or process where the engagement includes regression testing.

## Out of scope unless explicitly added

- universal model rankings;
- promises of production accuracy outside the evaluated distribution;
- unrestricted access to private evaluator truth;
- custom foundation-model training infrastructure;
- generic GPU hosting;
- unlimited integration work;
- a claim that a runnable environment is scientifically, Frontier, training, or commercially qualified;
- a claim that Veritas-directed data improves training without the corresponding controlled experiment.

## Change control

After the private evaluation begins, changes to model, harness, prompt, environment, task distribution, verifier, tools, permissions, seeds, or thresholds must either:

- create a new identified comparison condition; or
- invalidate/restart the affected comparison.

Post-hoc changes must not be silently folded into the original result.

## Acceptance criteria

The engagement is complete when:

- agreed runs are executed or a documented blocking incompatibility is established;
- outputs are bound to exact evaluated identities;
- the decision report answers the agreed question;
- failed/unknown gates remain visible;
- buyer-safe output contains no unauthorized evaluator truth or customer-confidential material;
- any stronger training, transfer, learning-efficiency, or commercial claim is withheld unless separately qualified.