# Veritas Paid-Pilot Launch Gate

This is the minimum checklist before accepting payment for the first design-partner evaluation.

## Must be true before accepting payment

### Product / release

- [ ] Veritas 0.9.1 Experimental Integrity merged to `main` after exact-head CI/Security and Training Value v3 evidence review.
- [ ] Veritas 0.10 Benchmark Qualification merged to `main` after retargeting and exact-head CI/Security/SRE/ProjectWorld qualification.
- [ ] `main` is protected against direct pushes and requires the agreed release checks.
- [ ] Commercial Evaluation Pack PR merged on top of the qualified release.
- [x] Primary commercial SKU defined as **Veritas SRE Evaluation Pack v1**.
- [x] SRE v3 has a qualified empirical candidate with 34 private-test cases and zero failed qualification gates.
- [x] ProjectWorld v2 has a qualified benchmark candidate and can serve as the second environment family.
- [x] First frozen SRE private suite is copied outside the public repository.
- [x] Private benchmark storage/disclosure/retirement policy documented.
- [x] OpenAI-compatible endpoint evaluation surface implemented for the SRE pack.
- [x] Local Hugging Face checkpoint evaluation surface implemented for the SRE pack.
- [x] Buyer-safe SRE report renderer implemented.
- [ ] Real-model commercial evidence workflow passes on at least two model families using the identical frozen panel.
- [ ] End-to-end paid-pilot dress rehearsal passes on the final release candidate.

### Private benchmark security

- [x] Future SRE qualification artifacts are sanitized so raw snapshots and per-scenario oracle outcomes are not persisted as long-lived public artifacts.
- [x] Exact SRE v3 private benchmark copied to private connected storage.
- [ ] Previously published raw SRE v3 Actions artifact removed/expired after the current fixed-panel model-evidence run no longer needs it.
- [ ] Commercial private-suite storage location, operator access policy and backup policy recorded outside the public repository.

### Commercial identity / payment — seller action required

- [ ] Seller legal/contracting name chosen.
- [ ] Business/billing email chosen.
- [ ] Invoice numbering convention chosen.
- [ ] Payment rail/account can receive the chosen pilot currency.
- [ ] Tax/withholding treatment checked for the seller/customer situation.
- [ ] Private pricing/discount authority documented outside the public repository.

### Contracting — seller/legal review required

- [ ] SOW/order form completed with seller identity.
- [ ] NDA/customer-paper process chosen.
- [ ] MSA or standalone terms path chosen.
- [ ] Software/private benchmark licensing boundary reviewed for the exact pilot data sources.
- [ ] IP treatment for customer inputs, trajectories, reports, adapters and publicity stated.
- [ ] DPA/security terms prepared if a pilot will process personal or customer-confidential data.

### Delivery

- [x] Customer onboarding checklist exists.
- [x] Evaluation acceptance criteria exist.
- [x] Versioned buyer-safe report workflow exists.
- [ ] Public pilot contact route configured with a business contact controlled by the seller.
- [ ] Credential exchange method chosen for customer endpoints.
- [ ] Retention/deletion terms can be recorded per pilot.
- [ ] Incident escalation/contact owner identified.
- [ ] First external design partner completes a dry run.

## Outreach can begin before every enterprise control is complete

The following do **not** block design-partner conversations:

- SOC 2;
- third-party penetration testing;
- 7B/frontier-model calibration;
- positive RL/SFT training-transfer proof;
- 0.11 industrial live-sandbox fidelity;
- external benchmark methodology review;
- correlation study with production SRE work.

They may become procurement requirements for a particular buyer, but they should be demand-driven rather than prerequisites invented in advance.

## First paid-pilot readiness threshold

Do not accept payment until the release, private-suite and seller/payment requirements above are satisfied. Do begin outreach once the real-model evidence workflow is green and a credible public product page/contact route exists.

The first paid pilot is intended to validate **decision usefulness**, not merely produce revenue: record what decision the customer was trying to make, what Veritas result changed or clarified that decision, and whether the customer would pay for a re-evaluation or a second environment.
