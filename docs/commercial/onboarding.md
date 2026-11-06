# Veritas Design-Partner Pilot Onboarding

## 1. Decision question

Before integration, define one primary decision the pilot should support. Examples:

- choose between two models or harnesses;
- identify the dominant failure modes in long-running work;
- test whether additional inference budget improves outcomes;
- determine whether a new tool/permission policy improves success safely;
- compare a before/after agent change.

The pilot should not begin with an undefined request to “benchmark our AI.”

## 2. Customer technical input

Preferred first-pilot integration:

- OpenAI-compatible `/v1/chat/completions` endpoint;
- model identifier;
- temporary/revocable API credential supplied out of band;
- endpoint/network restrictions if any;
- maximum input/output token limits;
- expected rate limits;
- retry policy;
- required system prompt or immutable harness instructions, if applicable.

Alternative integrations (agent endpoint, container, CLI, checkpoint) are scoped separately because they add integration work.

## 3. Evaluation constraints

Agree before the private run:

- model/harness version;
- task suite/version;
- attempts per task;
- token budget;
- tool-call/cost budget;
- wall-clock timeout;
- allowed tools/systems;
- retry policy;
- whether customer-managed inference is required;
- whether any model outputs are considered confidential.

## 4. Data/security

The standard CompanyWorld pilot is synthetic and does not require production customer data.

If the customer nevertheless supplies confidential data, prompts, logs, or credentials, the parties must additionally agree on:

- retention period;
- deletion method;
- permitted subprocessors;
- transmission/storage location;
- DPA/security requirements if personal data is involved;
- whether raw trajectories may be retained after the final report.

Never place customer credentials, private benchmark assets, or customer-confidential artifacts in the public GitHub repository.

## 5. Pre-run checklist

- [ ] Decision question written in one sentence.
- [ ] Customer technical owner identified.
- [ ] Commercial/contracting owner identified.
- [ ] SOW/order form agreed.
- [ ] Credential exchange channel agreed.
- [ ] Endpoint/harness dry run passed.
- [ ] Benchmark version and private-suite hash frozen.
- [ ] Manifest created.
- [ ] Evaluation budgets/retry rules signed off.
- [ ] Retention/deletion terms recorded if needed.

## 6. Support and escalation

During a pilot, classify issues as:

- **P0 — benchmark/security integrity:** suspected private-oracle leakage, credential exposure, corrupted private suite, or scoring integrity failure. Stop the affected run immediately.
- **P1 — evaluation blocked:** endpoint/harness failure prevents meaningful execution. Pause scoring and work with the customer technical owner.
- **P2 — isolated task/run issue:** record, quarantine the affected task, and continue if the remainder of the suite is valid.
- **P3 — enhancement/request:** schedule after the agreed pilot unless required for acceptance.

All changes that could affect scores are documented in the run record.

## 7. Readout

The standard readout should answer the original decision question first, then show the supporting scores, trajectories, failure modes, caveats, and recommended next actions. A re-evaluation can be quoted after the customer changes its model, prompt, tools, permissions, or harness.
