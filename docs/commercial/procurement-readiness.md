# Veritas Procurement-Readiness Checklist

This checklist tracks what is required to move from a technical benchmark to a repeatable enterprise evaluation product.

## Product identity and versioning

- [ ] Stable commercial product name and benchmark-version policy.
- [ ] Immutable benchmark manifest for every customer run.
- [ ] Release notes describing verifier, generator and task-distribution changes.
- [ ] Compatibility policy for old benchmark scores.
- [ ] Customer-visible status page or run-status mechanism.

## Evaluation delivery

- [ ] OpenAI-compatible model adapter.
- [ ] Generic HTTP agent adapter.
- [ ] Container/CLI adapter for customer-controlled agents.
- [ ] Per-run configuration for token, tool, time and retry budgets.
- [ ] Private benchmark seed management.
- [ ] Run cancellation and resume semantics.
- [ ] Complete trajectory export.
- [ ] Machine-readable and buyer-facing reports.

## Security and privacy

- [ ] Public/private benchmark isolation tested in release builds.
- [ ] Secrets redaction in model/tool logs.
- [ ] Customer-specific data retention/deletion configuration.
- [ ] TLS and endpoint allowlisting.
- [ ] Dependency/container inventory.
- [ ] Vulnerability scanning on every release.
- [ ] Documented incident-response process.
- [ ] Subprocessor inventory for hosted services.
- [ ] Customer-managed inference supported where required.

## Benchmark validity

- [x] Private ground truth separated from public observations.
- [x] Reward-hacking/adversarial policy tests.
- [x] Oracle/public-reference solvability checks.
- [x] Deterministic benchmark hashes.
- [x] Multi-level investigation/action/control environments.
- [x] Initial real open-model calibration ladder.
- [ ] Stronger 3B–frontier model capability curve.
- [ ] Larger stratified calibration sample with confidence intervals.
- [ ] External/customer agent results.
- [ ] Correlation study with at least one real operational workflow.

## Training-value proof

- [ ] Pre-training held-out baseline.
- [ ] Train-world trajectory generation.
- [ ] Reproducible SFT/RL adaptation run.
- [ ] Fresh-world held-out post-training evaluation.
- [ ] Report capability improvement and regressions.
- [ ] Separate train/dev/private seeds and object identities.

## Commercial operations

- [ ] Paid pilot statement of work template.
- [ ] Pricing/quoting policy.
- [ ] Customer onboarding checklist.
- [ ] Evaluation acceptance criteria.
- [ ] Support/escalation process.
- [ ] Invoice/payment workflow.
- [ ] Renewal/re-evaluation offer.

## Legal/compliance preparation

- [ ] Entity/contracting details.
- [ ] Master services agreement or customer paper review process.
- [ ] Data processing addendum where customer data is processed.
- [ ] Confidentiality/NDA process.
- [ ] Benchmark and software licensing terms.
- [ ] IP ownership statement for customer trajectories and reports.
- [ ] Privacy policy for any hosted service.

## Enterprise trust evidence

Longer-term enterprise procurement may require certifications or third-party assurance. These should follow actual customer demand rather than delaying early pilots.

Potential future evidence includes SOC 2, penetration testing, formal secure-SDLC controls, business-continuity documentation and external benchmark-methodology review.
