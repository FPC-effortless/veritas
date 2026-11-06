# Veritas Procurement-Readiness Checklist

This is a buyer-facing guide, not a separate release or payment authorization. The canonical software release is **Veritas 0.11.0** / **`v0.11.0`**, and the primary commercial SKU is **Veritas SRE Evaluation Pack v1**. CompanyWorld remains available for scoped pilots and training experiments.

Use [Build status](../../BUILD_STATUS.md) for release identity, scientific boundaries and exact-candidate gates; use the [paid-pilot launch checklist](launch-checklist.md) for conditions before accepting payment. A checked item below summarizes recorded repository/release evidence, not a fresh audit of seller accounts, customer delivery, or third-party certification. New development candidates still need their own exact-head checks and authorization.

## Recorded software and delivery evidence

The [marketplace release packet](marketplace-release.md), [commercial package](README.md) and [launch checklist](launch-checklist.md) record:

- [x] Immutable `v0.11.0` GitHub release with wheel/sdist, checksums, SBOM, provenance and portability identities.
- [x] Root Apache-2.0 software grant and explicit restricted-private-asset boundary in [LICENSING.md](../../LICENSING.md).
- [x] Protected-main and required-check controls recorded for the released commercial line; verify live settings before a new release.
- [x] Frozen, sealed SRE v4 assets stored outside the public repository, with public immutable identities and aggregate qualification evidence.
- [x] OpenAI-compatible endpoint and local checkpoint evaluation surfaces for the SRE pack.
- [x] Two model-family runs and an authenticated customer-equivalent endpoint dress rehearsal on the exact frozen panel.
- [x] Buyer-safe scorecards/report tooling, versioned run identities, privileged trajectory capture and evaluation budgets.
- [x] HUD/Prime adapter compatibility, deterministic identity/reset and canonical reward-parity evidence.
- [x] Public buyer-safe commercial inquiry form, onboarding, acceptance criteria, SOW/invoice templates and security operating-policy templates.

These are scoped implementation and release facts. They do not establish Frontier Qualification, external marketplace distribution, production-workflow correlation, or readiness to accept a particular customer's payment.

## Seller and first-customer gates — still require action

Use the full [launch checklist](launch-checklist.md), [contracting checklist](legal/contracting-checklist.md), [onboarding](onboarding.md) and [evaluation acceptance criteria](evaluation-acceptance.md) for the actual transaction. The following remain unchecked here:

- [ ] Seller legal/contracting identity, business/billing email and invoice numbering selected.
- [ ] Payment rail/account, currency, tax/withholding treatment and private pricing authority established.
- [ ] SOW/order form completed; NDA/MSA or customer-paper route, licensing and IP terms reviewed for the transaction.
- [ ] DPA/security terms approved when personal or customer-confidential data is involved.
- [ ] Private credential-exchange channel agreed; never send secrets through the public inquiry form.
- [ ] Retention/deletion terms recorded for the first pilot and actual subprocessors identified.
- [ ] Incident escalation/contact owner identified for the first pilot.
- [ ] Commercial private-suite backup/recovery policy recorded outside the public repository and tested by the seller.
- [ ] First external design partner completes a dry run and the agreed evaluation/readout acceptance process.

The standard synthetic pilot does not require production customer data. Model/harness identity, suite hash, budgets, attempts and retry rules must be agreed before a private run. Stop affected runs on suspected leakage or scoring-integrity failure.

## External distribution — not implied by adapter tests

The [external submission status](EXTERNAL_SUBMISSION_STATUS.md) is a dated operating record, not evidence that account-native deployment has subsequently occurred. Consult the [HUD](hud-submission.md) and [Prime](prime-submission.md) submission packets for required evidence.

- [ ] Seller-account HUD deployment, inspected HUD-native run and DataVendor intake confirmation.
- [ ] Sanitized Prime Hub publication, clean external installation, Hosted Evaluation and applicable submission acknowledgement.

Private benchmark rows, hidden labels and customer secrets must not be uploaded to public listings, issues or artifacts. External actions are complete only when the corresponding platform evidence exists.

## Additional delivery controls — scope to a real buyer

The standard pilot is operator-led; it does not promise a self-service SaaS dashboard. Alternative agent endpoints, containers and CLI harnesses are separately scoped in [onboarding](onboarding.md). Check the actual deployment rather than treating these as completed hosted-service capabilities:

- [ ] Customer-visible run status beyond direct operator communication, if required.
- [ ] Production-grade cancellation/resume and customer-specific hosted retention/deletion, if required.
- [ ] Arbitrary HTTP agent or customer container/CLI integration accepted for the agreed harness.
- [ ] Endpoint hostname/network policy, TLS requirements and secrets-redaction behavior verified for the selected runner and logs.
- [ ] Customer-specific subprocessor register, security/data-flow diagram and incident/continuity contacts populated.
- [ ] Privacy policy published if a hosted customer-facing service processes customer data.

These controls are not substituted by a software release or a successful synthetic test. See [security and delivery](security-and-delivery.md) for deployment boundaries and recommended controls.

## Scientific and training claims remain scoped

SRE v4 scientific qualification and the recorded small-model execution/reproducibility evidence do **not** establish frontier-agent discrimination or general production utility. CompanyWorld has replicated within-family held-out transfer results recorded in [Build status](../../BUILD_STATUS.md); those are not broad source/grammar-disjoint transfer proof or a customer-specific commercial guarantee.

- [ ] Frontier/strong-agent comparative capability evidence for the proposed commercial claim.
- [ ] Customer/external-agent decision-usefulness evidence for the agreed pilot.
- [ ] Correlation with a real operational workflow, if claimed.
- [ ] For a training claim: frozen held-out baseline, approved split-isolated corpus, reproducible adaptation, fresh IID/OOD/adversarial evaluation and verified improvement for that exact suite/model/harness.

## Enterprise trust evidence — deliberately deferred

SOC 2, third-party penetration testing, formal business-continuity evidence and external methodology review are **not prerequisites for the first synthetic design-partner pilot**. Add them when a real buyer requires them; do not present templates, internal tests or this checklist as external certification.
