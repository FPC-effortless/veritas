# Veritas Paid-Pilot Launch Gate

This is the minimum checklist before accepting payment for the first design-partner evaluation.

## Must be true before accepting payment

### Product / release

- [x] Veritas 0.9.1 Experimental Integrity merged to `main` after exact-head CI/Security and Training Value v3 evidence review.
- [x] Veritas 0.10 Benchmark Qualification merged to `main` after exact-head CI/Security/SRE/ProjectWorld qualification.
- [ ] `main` is protected against direct pushes and requires the agreed release checks.
- [ ] Commercial Evaluation Pack PR merged on top of the qualified release.
- [x] Primary commercial SKU defined as **Veritas SRE Evaluation Pack v1**.
- [x] SRE v4 passes the **current** qualification gate set with material private support across all four causal classes.
- [x] SRE v3 is explicitly retired from private scoring after class-coverage failure under the stronger gate and prior public artifact exposure.
- [x] ProjectWorld v2 has a qualified benchmark candidate and can serve as the second environment family.
- [x] OpenAI-compatible endpoint evaluation surface implemented for the SRE pack.
- [x] Local Hugging Face checkpoint evaluation surface implemented for the SRE pack.
- [x] Buyer-safe SRE report renderer implemented with balanced accuracy, macro F1 and majority-baseline reporting.
- [x] SRE v4 is frozen in controlled private storage with candidate ID and SHA-256 pinned.
- [ ] Manual real-model commercial evidence workflow passes on at least two model families using the identical frozen v4 panel.
- [ ] End-to-end paid-pilot dress rehearsal passes on the final release candidate.

### Private benchmark security

- [x] Public SRE qualification artifacts omit raw snapshots, per-scenario oracle outcomes and private labels.
- [x] Public model-evidence artifacts omit scenario IDs, per-case predictions and per-case expected labels.
- [x] Public CI verifies the frozen v4 release identity rather than reacquiring feeds or reconstructing the benchmark.
- [x] The model-evidence workflow no longer transfers private truth between jobs; one ephemeral runner consumes the private bundle directly.
- [x] SRE v3 is treated as consumed/retired rather than made "private again" by copying it elsewhere.
- [x] Fresh SRE v4 private bundle is stored outside the public repository; its immutable checksum is pinned publicly.
- [ ] Private bundle URL/checksum and all five sealed-identity secrets are configured for the manual evidence workflow, or an equivalent self-hosted/private evaluator path is documented.
- [ ] Commercial private-suite backup/recovery policy is recorded outside the public repository.

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
- broad cross-domain RL/SFT transfer proof;
- 0.11 industrial live-sandbox fidelity;
- external benchmark methodology review;
- correlation study with production SRE work.

They may become procurement requirements for a particular buyer, but they should be demand-driven rather than prerequisites invented in advance.

## First paid-pilot readiness threshold

Do not accept payment until the release, frozen-private-suite and seller/payment requirements above are satisfied. Design-partner outreach can begin now that SRE v4 is qualified and frozen, but the exact-panel real-model evidence run should be completed before representing the pack as calibrated for paid use.

The first paid pilot is intended to validate **decision usefulness**, not merely produce revenue: record what decision the customer was trying to make, what Veritas result changed or clarified that decision, and whether the customer would pay for a re-evaluation or a second environment.
