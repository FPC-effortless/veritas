# Veritas Procurement-Readiness Checklist

This checklist distinguishes **paid-design-partner blockers** from later enterprise-procurement work. A checked item means there is working code or a documented operating artifact in this repository; it does not imply third-party certification.

## Product identity and versioning

- [x] Stable first commercial line: **Veritas CompanyWorld Pilot v1**.
- [x] Immutable evaluation manifest object for customer runs.
- [x] Release/score-compatibility policy documented.
- [ ] First commercial GitHub release/tag published from protected `main`.
- [ ] Customer-visible run-status mechanism beyond direct operator communication.

## Evaluation delivery

- [x] OpenAI-compatible model endpoint adapter.
- [x] Per-run model/token/timeout metadata and operational budget support.
- [x] Privileged trajectory capture/export from evaluated episodes.
- [x] Machine-readable result and buyer-facing report tooling.
- [x] Customer-controlled inference can be used through the endpoint path.
- [ ] Generic arbitrary HTTP agent adapter.
- [ ] Standard customer container/CLI adapter contract.
- [ ] Production-grade run cancellation/resume orchestration.
- [ ] Private benchmark seed storage outside the public repository completed for the first paid suite.

## Security and privacy

- [x] Public/private benchmark isolation covered by regression tests.
- [x] API credentials are read from environment variables and are not written into evaluation reports.
- [x] Dependency/security scanning workflows exist.
- [x] Incident-response process documented.
- [x] Data-retention policy template documented.
- [x] Customer-managed inference path supported for the standard endpoint pilot.
- [ ] General-purpose secrets redaction across every possible customer harness/log surface.
- [ ] Network/TLS endpoint allowlisting policy enforced in code.
- [ ] Release SBOM/container inventory artifact.
- [ ] Customer-specific retention/deletion settings implemented in hosted orchestration.
- [ ] Customer-specific subprocessor register populated for the actual deployment stack.

## Benchmark validity

- [x] Private ground truth separated from public observations.
- [x] Reward-hacking/adversarial policy tests.
- [x] Oracle/public-reference solvability checks.
- [x] Deterministic benchmark hashing/manifest mechanisms.
- [x] Multi-level investigation/action/control environments.
- [x] Initial real open-model calibration work.
- [x] Foundry materialization hides latent difficulty/randomness/failure-schedule state from the evaluated agent.
- [ ] Stronger 3B-to-frontier comparative capability curve completed and retained as a commercial artifact.
- [ ] Larger stratified calibration sample with confidence intervals.
- [ ] External/customer agent result.
- [ ] Correlation study with at least one real operational workflow.

## Training-value proof

A training workflow exists, but **positive held-out capability transfer is not yet a commercial claim**.

- [ ] Frozen pre-training held-out baseline for the current pilot suite.
- [ ] Approved train-world trajectory corpus for the commercial version.
- [ ] Reproducible SFT/RL adaptation run against the hardened task materializer.
- [ ] Fresh-world IID/OOD/adversarial post-training evaluation.
- [ ] Positive held-out capability improvement demonstrated and regression-checked.
- [x] Train/IID/OOD/adversarial world separation is represented in the foundry design.

## Commercial operations

- [x] Paid pilot scope documented.
- [x] Statement of Work template.
- [x] Customer onboarding checklist.
- [x] Evaluation acceptance criteria.
- [x] Support/escalation process included in the SOW/onboarding package.
- [x] Invoice template.
- [x] Re-evaluation/renewal option defined as a pilot extension.
- [ ] Seller's private pricing/quoting policy finalized.
- [ ] Contracting entity details inserted into commercial documents.
- [ ] Payment rail/account and invoice numbering process activated.

## Legal/compliance preparation

- [x] Data-retention, incident-response, subprocessor, and licensing-boundary preparation documents exist.
- [x] NDA/MSA/SOW/DPA/security/publicity contracting checklist exists.
- [ ] Contracting entity/legal name finalized for invoices and agreements.
- [ ] Final MSA/customer-paper review process chosen.
- [ ] Final DPA approved for any pilot that processes customer personal/confidential data.
- [ ] Final NDA/confidentiality template or customer-paper process chosen.
- [ ] Final public software license and private benchmark license terms chosen.
- [ ] Final IP ownership language approved for customer trajectories/reports/adapters.
- [ ] Privacy policy published if a hosted customer-facing service processes customer data.

## Repository/release controls

- [ ] Protect `main` against direct pushes.
- [ ] Require `CI / Required` and Security checks before merge.
- [ ] Publish the first `v0.5.0` release only after the commercial freeze PR passes all gates.
- [ ] Store private paid-evaluation assets outside the public Git repository.

## Enterprise trust evidence — deliberately deferred

SOC 2, third-party penetration testing, formal business-continuity evidence, external methodology review, and more extensive secure-SDLC controls are useful for larger procurement processes but are **not prerequisites for the first synthetic design-partner pilot**. Add them when a real buyer requires them.
