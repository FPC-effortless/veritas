# Veritas Paid-Pilot Launch Gate

This is the minimum checklist before accepting payment for the first design-partner evaluation. It is intentionally stricter than the threshold for marketplace submission or design-partner outreach.

## Must be true before accepting payment

### Product / release

- [x] Veritas 0.9.1 Experimental Integrity merged to `main` after exact-head evidence review.
- [x] Veritas 0.10 Benchmark Qualification merged to `main` after exact-head CI/Security/SRE/ProjectWorld qualification.
- [x] Veritas **0.11.0 Commercial Portability** merged to `main` and published as immutable GitHub release `v0.11.0`.
- [x] `main` rejects direct content writes and requires the repository release checks through the active ruleset.
- [x] Commercial Evaluation Pack PR #61 merged on top of the qualified release line.
- [x] Primary commercial SKU defined as **Veritas SRE Evaluation Pack v1**.
- [x] SRE v4 passes the current scientific qualification gate set with material private support across all four causal classes.
- [x] SRE v3 is explicitly retired from private scoring after class-coverage failure under the stronger gate and prior public artifact exposure.
- [x] ProjectWorld v2 has a qualified benchmark candidate and can serve as the second environment family.
- [x] OpenAI-compatible endpoint evaluation surface implemented for the SRE pack.
- [x] Local Hugging Face checkpoint evaluation surface implemented for the SRE pack.
- [x] Buyer-safe SRE report renderer implemented with balanced accuracy, macro F1 and majority-baseline reporting.
- [x] SRE v4 is frozen in controlled private storage with candidate ID and SHA-256 pinned.
- [x] Manual real-model commercial evidence workflow passed on two model families using the identical frozen v4 panel.
- [x] End-to-end paid-pilot dress rehearsal passed on the commercial release line using the authenticated OpenAI-compatible endpoint path.
- [x] HUD and Prime portability adapters passed clean external install/package validation, deterministic identity/reset and canonical reward-parity checks.
- [x] Root Apache-2.0 license plus explicit commercial-private licensing policy are part of the 0.11 release.
- [x] Release artifacts include wheel/sdist, checksums, SBOM, provenance and pinned portability identities.

### Private benchmark security

- [x] Public SRE qualification artifacts omit raw snapshots, per-scenario oracle outcomes and private labels.
- [x] Public model-evidence artifacts omit scenario IDs, per-case predictions and per-case expected labels.
- [x] Public CI verifies the frozen v4 release identity rather than reacquiring feeds or reconstructing the benchmark.
- [x] The model-evidence workflow no longer transfers private truth between jobs; one ephemeral runner consumes the private bundle directly.
- [x] SRE v3 is treated as consumed/retired rather than made "private again" by copying it elsewhere.
- [x] Fresh SRE v4 private bundle is stored outside the public repository; its immutable checksum is pinned publicly.
- [x] The sealed private-release path and canonical identities were sufficient to complete both real-model evidence and pilot-dress-rehearsal workflows against the exact frozen panel.
- [ ] Commercial private-suite backup/recovery policy is recorded outside the public repository and has been tested by the seller.

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
- [ ] Software/private benchmark licensing boundary reviewed for the exact pilot transaction and data sources.
- [ ] IP treatment for customer inputs, trajectories, reports, adapters and publicity stated in the transaction documents.
- [ ] DPA/security terms prepared if a pilot will process personal or customer-confidential data.

### Delivery

- [x] Customer onboarding checklist exists.
- [x] Evaluation acceptance criteria exist.
- [x] Versioned buyer-safe report workflow exists.
- [x] Public buyer-safe inquiry route exists through the repository's **Commercial evaluation inquiry** issue template.
- [ ] Private credential-exchange channel chosen for the first customer; credentials must never be placed in the public issue route.
- [ ] Retention/deletion terms recorded for the first pilot.
- [ ] Incident escalation/contact owner identified for the first pilot.
- [ ] First external design partner completes a dry run.

### Marketplace / external distribution

These are required to call the release externally distributed, but they do not block direct private-pilot outreach.

#### HUD / DataVendor

- [ ] DataVendor vendor organization setup completed, HUD review passed and vendor NDA signed for Tier 1 listing access.
- [ ] Veritas SRE v1 added as one managed RL/evaluation environment using the private-boundary rules in `datavendor-listing.md`.
- [ ] Tier 1 DataVendor listing submitted for review; live/approved is the stronger completion state.
- [ ] If the seller workflow exposes HUD-native deployment, exact `v0.11.0` SRE HUD package deployed from the seller account.
- [ ] At least one HUD-native task/evaluation run completes and is inspected for reward/grader/private-data issues before claiming HUD-native external validation.
- [ ] Tier 2+ brief access requested only if the seller intends to respond to custom buyer Project briefs.

#### Prime Intellect

- [ ] Private Hub proof completed with the operator package or explicitly skipped in favor of the public sample.
- [ ] Sanitized/public `veritas-sre-open` package pushed to the Prime Intellect Environments Hub.
- [ ] Clean install of the Hub-hosted Prime environment succeeds outside the developer checkout.
- [ ] At least one Prime Hosted Evaluation completes end to end with no private SRE material exposed.
- [ ] Prime environment/partner/bounty application references the live Hub artifact and immutable Veritas release.

See `marketplace-release.md`, `hud-submission.md`, `datavendor-listing.md`, and `prime-submission.md` for the external submission packets.

## Outreach can begin before every enterprise control is complete

The following do **not** block design-partner conversations:

- SOC 2;
- third-party penetration testing;
- 7B/frontier-model calibration;
- broad cross-domain RL/SFT transfer proof;
- 0.12 industrial live-sandbox fidelity;
- external benchmark methodology review;
- correlation study with production SRE work.

They may become procurement requirements for a particular buyer, but they should be demand-driven rather than prerequisites invented in advance.

## First paid-pilot readiness threshold

The software, qualified frozen benchmark, real-model evidence, release, portability layer and endpoint dress rehearsal are now complete. The remaining blockers to accepting payment are seller-controlled commercial administration plus the first customer-specific delivery controls: legal identity/payment rail, transaction documents, private credential channel, retention/deletion terms and incident owner.

The first paid pilot is intended to validate **decision usefulness**, not merely produce revenue: record what decision the customer was trying to make, what Veritas result changed or clarified that decision, and whether the customer would pay for a re-evaluation or a second environment.
