# Veritas “Do Not Build” Architecture Policy

Veritas is a high-assurance capability foundry. Its scarce engineering effort belongs in
environment correctness, verifier trust, frontier utility, semantic portability, diagnostic
value, and procurement-grade evidence. Commodity infrastructure remains an integration unless a
written architecture decision proves that integration cannot preserve a required Veritas
invariant.

## Presumptive non-goals

The following are not Veritas product lines:

- a full reinforcement-learning trainer;
- a model-serving platform;
- a hyperscale sandbox cloud;
- a generic human/expert marketplace;
- a benchmark aggregator;
- the largest harness catalog;
- a generic agent framework;
- a replacement for supported target runtimes.

“Do not build” is a rebuttable architecture presumption, not a ban on adapters. Veritas may define
contracts, conformance tests, buyer-safe evidence, and thin reference implementations needed to
make an external system trustworthy.

## Required proposal evidence

Any proposal that enters a presumptive non-goal must answer all of the following before
implementation approval:

1. Which Veritas assurance invariant or buyer requirement cannot be satisfied through an
   integration?
2. Which existing external systems were evaluated, at exact versions, and what evidence shows the
   integration is insufficient?
3. What is the smallest Veritas-owned boundary that closes the demonstrated gap?
4. How does the work strengthen environment correctness, verifier trust, frontier utility,
   portability, or diagnosis?
5. Which commodity responsibilities remain delegated?
6. What is the exit or replacement path if an external integration later becomes adequate?
7. What tests falsify the claim that new owned infrastructure is necessary?

Cost, convenience, competitor feature count, and a desire for tighter control are not sufficient
on their own.

## Review and enforcement

- Open architecture work through the repository architecture-proposal issue form.
- Use the architecture decision template for an accepted decision.
- Pull requests must link the proposal/decision when they enter a presumptive non-goal.
- Reviewers assess product identity, integration evidence, security/privacy, maintenance burden,
  and falsifiers independently.
- A proposal without the required evidence remains `UNKNOWN`/unapproved; silence is not approval.

Release or commercial authority is not created by approval of an architecture decision.
