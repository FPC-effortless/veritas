# Governance

The ecosystem uses a maintainer-led model in this shared repository. Veritas owns
assurance semantics; Forge owns reproducible data releases; TrainLab owns bounded
execution records; Research Lab OS is an experimental coordination layer. The
[architecture policy](docs/architecture/do-not-build-policy.md) and component contracts
define the boundaries. There is no separate foundation, elected council or legal
entity representation established by this file.

## Decisions and review

Use issues and PRs for public, buyer-safe discussion. Architecture changes use the
existing architecture proposal form, including integration alternatives and
falsifiers. Maintainers decide scope and acceptance based on the user requirement,
compatibility, verification, privacy, source rights and maintenance cost. When a
decision is disputed, request a written rationale and a focused follow-up proposal;
keep private customer or evaluator material outside public discussion.

Implementation review and scientific review are separate. Authors must not
self-attest independent scientific replication, qualification or source permission.
Repository code changes follow [AGENTS.md](AGENTS.md), including its independent
review and exact-head provenance requirements. A code-review PASS does not approve
an experiment, production deployment, private benchmark or commercial release.

## Licensing and conflicts

Public project-authored code remains under the existing Apache-2.0 grant unless
a file carries its own applicable notice. Private commercial assets and third-party
material retain the boundaries in [LICENSING.md](LICENSING.md). Paid work may fund
maintenance, customer integrations, private evaluations or managed operations;
payment cannot change a verifier result, remove a negative finding or waive an
integrity gate. Disclose relevant commercial interests when reviewing a claim.

## Releases and participation

Each component retains its package/import identity and release contract. Source
co-location does not imply equal maturity or synchronized versions. Maintainers
may accept contributors and assign bounded maintenance responsibilities through
public review; no appointment or permissions change is implied by a contribution.
There is no automatic release or publication from passing the ecosystem demo.
Canonical Veritas release authority stays in [BUILD_STATUS.md](BUILD_STATUS.md)
and the release workflows. Commercial administration and customer-specific
acceptance stay in the [existing launch gate](docs/commercial/launch-checklist.md).

This project welcomes respectful, evidence-backed questions and disagreement.
Address behavior and technical claims rather than personal attributes. Bring
conduct concerns privately to a maintainer using a channel they have established;
no private contact details are invented here.
