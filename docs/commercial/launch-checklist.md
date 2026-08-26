# Veritas Paid-Pilot Launch Gate

This is the minimum checklist before accepting money for the first design-partner evaluation.

## Must be true before accepting payment

### Product/release

- [ ] Commercial freeze PR merged to `main`.
- [ ] Exact release commit passes CI and Security.
- [ ] `main` is protected against direct pushes and requires the agreed checks.
- [ ] `v0.5.0` GitHub release published.
- [ ] Commercial benchmark version is `companyworld-pilot-v1`.
- [ ] First private paid-evaluation suite is stored outside the public repository.
- [ ] Private-suite content hash recorded.
- [ ] End-to-end pilot dress rehearsal passed on the release candidate.

### Commercial identity/payment

- [ ] Seller legal/contracting name chosen.
- [ ] Billing email chosen.
- [ ] Invoice numbering convention chosen.
- [ ] Payment rail/account can receive the chosen pilot currency.
- [ ] Tax/withholding treatment checked for the seller/customer situation.
- [ ] Private pricing/discount authority documented.

### Contracting

- [ ] SOW/order form ready with seller identity.
- [ ] NDA/customer-paper process chosen.
- [ ] MSA or standalone terms path chosen.
- [ ] Software/private benchmark licensing boundary stated.
- [ ] IP treatment for customer model inputs, trajectories, reports, adapters, and publicity stated.
- [ ] DPA/security terms added if the pilot will process personal/customer-confidential data.

### Delivery

- [ ] Pilot contact route configured on the public site.
- [ ] Customer onboarding checklist ready.
- [ ] Credential exchange method chosen.
- [ ] Retention/deletion terms can be recorded.
- [ ] Incident escalation owner identified.
- [ ] Final report/readout workflow tested.

## Can happen after outreach begins

The following do **not** block beginning sales conversations:

- SOC 2;
- third-party penetration testing;
- broad generic agent/container adapters;
- 7B/frontier-model calibration;
- positive RL/SFT training-transfer proof;
- empirical operational-world compiler completion;
- external benchmark methodology review;
- correlation study with real production work.

## Can happen after the first customer pays

Prioritize in this order based on buyer demand:

1. requested integration adapter;
2. customer-specific private world/task extensions;
3. repeated regression/re-evaluation workflow;
4. customer-specific security/procurement controls;
5. training-value experiment if the buyer wants capability development rather than evaluation only;
6. broader calibration and external validity work.

Do not delay the first sale to complete research items that the first buyer does not require.
