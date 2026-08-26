# Veritas Licensing Strategy — Decision Memo

Status: decision framework, not a final license grant. Do not add a repository LICENSE file until the owner deliberately chooses the public/private boundary and legal terms.

## Assets with different commercial value

Veritas contains several separable assets:

1. **Runtime/framework code** — environment models, tool/runtime interfaces, verifier plumbing, calibration and foundry infrastructure.
2. **Public development tasks/fixtures** — examples needed to integrate and test an agent.
3. **Private benchmark worlds/seeds/oracles** — evaluator-only truth that loses value if broadly disclosed.
4. **Private adversarial suites** — exploit/regression tasks created from model failures.
5. **Customer-specific adapters/tasks** — potentially derived from confidential customer workflows.
6. **Evaluation reports and trajectories** — customer-specific outputs.

These should not automatically share one license.

## Recommended commercial boundary

A practical design-partner model is:

- keep enough framework/runtime code inspectable to reduce integration friction and establish technical credibility;
- keep private benchmark seeds, hidden truth, oracles, adversarial holdouts and customer-specific task distributions out of public release;
- sell evaluation access, private benchmark execution, private-world generation, reporting and training/evaluation programs rather than selling static task files;
- contractually prohibit benchmark extraction, oracle reconstruction and redistribution of private evaluation material.

## Open-source options to evaluate

If the framework is intentionally open-sourced, consider a standard permissive license such as Apache-2.0 for framework code only, while private benchmark assets remain proprietary and are never included under that license.

If maintaining exclusive commercial leverage over the framework itself is more important, keep the repository proprietary or move public framework code into a separate explicitly licensed repository.

This memo does not select either option. The final choice should consider investor strategy, contribution goals, patent position, customer procurement expectations and whether an open framework increases demand for private evaluations.

## Required decision before broad distribution

Document in writing:
- which repositories/packages are public;
- which benchmark assets are evaluator-only;
- whether framework contributions are accepted;
- contributor/IP terms;
- customer rights in reports and customer-specific adapters;
- restrictions on private benchmark extraction and redistribution;
- whether evaluation outputs may be used in anonymized aggregate research.

## Procurement position before final license

For paid pilots, rights can be granted in the MSA/SOW even before a public framework license is selected. Do not imply that absence of a repository LICENSE file grants customers redistribution rights.
