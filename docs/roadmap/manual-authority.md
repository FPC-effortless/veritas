# External and manual authority work

ROADMAP-EXT-001 defines how Veritas represents work that remains necessary to a product,
scientific, or commercial outcome but cannot be autonomously executed merely because a coding agent
can see it in the roadmap.

This is a coordination policy. It does not grant access to accounts, credentials, private evidence,
paid compute, legal authority, payment rails, release authority, or qualification authority.

## Core rule

A roadmap dependency can be real without being agent-claimable.

Work requiring an external account, private evidence, legal/commercial authority, paid-resource
approval, or an owner decision must remain visible as an explicit authority dependency. It must not
be advertised as ordinary READY implementation work, and a normal `/claim` must not be interpreted
as permission to cross that boundary.

Repository preparation may proceed separately when an issue explicitly defines a bounded,
agent-owned preparation subtask with disjoint ownership. Preparation never satisfies the external or
manual authority requirement by itself.

## Separate axes

Do not collapse these concepts:

- **coordination state** — `BLOCKED`, `READY`, `CLAIMED`, `REVIEW`, `DONE`, or `SUPERSEDED`;
- **authority requirement** — who or what must authorize an action outside ordinary repository work;
- **work class** — implementation, experiment, qualification, external/manual, convergence, release,
  or another completion class;
- **qualification state** — scientific, Frontier, training, commercial, or other evidence status;
- **merge authority** — whether a reviewed code/documentation change may be merged;
- **release/publish authority** — whether an artifact may be released, listed, submitted, or exposed.

For example, creating a seller account is not scientific qualification, and a scientifically
qualified environment does not authorize opening a seller account. Likewise, a green implementation
PR cannot satisfy a private-evidence gate that was never run.

## Authority classes

Authority requirements are a list, because one task may require more than one class.

### `EXTERNAL_ACCOUNT`

Use when completion requires an authenticated account or account-native action outside the repository.
Examples include vendor onboarding, marketplace listing, platform-native deployment, signing into a
provider, or obtaining account-native run identifiers.

A coding agent may prepare configuration, documentation, packages, or commands when separately owned,
but must not create an account, authenticate with private credentials, accept account terms, or claim
account-native evidence without explicit authority and access.

### `MANUAL_PRIVATE_EVIDENCE`

Use when completion requires access to sealed/private rows, decryption material, confidential buyer
artifacts, private model outputs, protected evaluation results, or another evidence source that is not
available to the ordinary agent lane.

Public or synthetic substitutes may exercise infrastructure, but they do not turn missing private
evidence into PASS. Evidence references recorded in roadmap metadata must be opaque/buyer-safe and
must never contain secrets or private payloads.

### `LEGAL/COMMERCIAL_AUTHORITY`

Use for legal entity choices, contracting identity, NDA/SOW acceptance, tax/withholding decisions,
commercial terms, pricing commitments, payment activation, or any action that creates a legal or
commercial obligation.

An agent may draft or validate non-binding materials when explicitly assigned, but cannot accept terms,
make binding representations, activate payment, or treat a draft as owner approval.

### `PAID_COMPUTE_AUTHORITY`

Use when a run may incur paid compute, model, API, storage, or other metered spend that has not already
been authorized by a bounded budget policy.

Free/public CI, an already-authorized fixed credit allocation, or a no-spend local run does not require
this class merely because the equivalent service can be paid. If a run can cross into billable usage,
the authority boundary applies before dispatch.

Approval to spend is not evidence that the resulting experiment passed. The experiment and its
evidence remain governed by their own protocol.

### `OWNER_DECISION`

Use for an explicit product/research/business choice that cannot be inferred safely from repository
state: publish vs keep private, proceed vs defer, choose a seller identity, approve external egress,
select a contractual option, or intentionally accept a trade-off that policy leaves to the owner.

Silence is not approval. An implementation recommendation may narrow the decision, but cannot replace
it.

## Proposed roadmap metadata

Authority metadata is orthogonal to execution state and should be machine-readable. A compatible
manifest representation is:

```yaml
authority:
  required:
    - EXTERNAL_ACCOUNT
    - OWNER_DECISION
  status: PENDING
  preparation_allowed: true
  preparation_scope: "buyer-safe package and submission checklist only"
  evidence_refs: []
```

Normative semantics:

- `required` is a unique list containing only the five authority classes in this document;
- `status` is `NOT_REQUIRED`, `PENDING`, `SATISFIED`, or `DEFERRED`;
- a non-empty `required` list must not use `NOT_REQUIRED`;
- `SATISFIED` requires an auditable non-secret evidence/decision reference appropriate to every
  required class;
- `preparation_allowed` does not authorize the external/manual action;
- `preparation_scope` must be explicit when preparation is allowed;
- `evidence_refs` contain opaque references/identifiers, never credentials, keys, private rows, or
  protected payloads.

Until this metadata is implemented by the canonical roadmap schema, issues should state equivalent
requirements explicitly in their Work Contract or dependency text and remain fail-closed.

## Claim behavior

Normal agent claiming must follow this decision rule:

1. If no authority class is required, normal coordination rules apply.
2. If authority is `PENDING` or `DEFERRED` and the issue is authority-only, reject normal `/claim`.
3. If the issue explicitly permits an agent-owned preparation subtask, only that bounded preparation
   scope may be claimed. The authority action remains pending and outside the claim.
4. If authority is `SATISFIED`, normal `/claim` may proceed only if all other dependency, ownership,
   branch, and work-class rules are also satisfied.
5. A `/claim`, `/handoff`, merged PR, or green CI run can never change authority status to `SATISFIED`.

Authority-only work should therefore normally be represented as BLOCKED/external rather than ordinary
READY code work. If the roadmap later adds a dedicated external/manual execution state, it must remain
separate from environment/experience maturity and qualification states.

## Preparation subtask pattern

When useful coding work can happen before a human/account action, split it explicitly:

```text
PREP-001 — agent-claimable
  ownership: docs/package/tests only
  output: buyer-safe package + validation evidence

EXT-001 — external/manual authority
  authority: EXTERNAL_ACCOUNT + OWNER_DECISION
  depends on: PREP-001
  output: platform/account-native acknowledgement
```

The preparation ticket may become DONE while the external ticket remains pending. Product work may
then depend on either one according to what it actually needs.

Do not hide the external requirement by keeping one broad ticket READY and assuming an agent will stop
at the right moment.

## Dependency semantics

A blocked product or experiment may reference an authority requirement as an explicit dependency.
This is not a code-merge dependency.

Recommended meaning when dependency kinds are available:

- account onboarding, account-native listing/run -> `external_authority`;
- sealed/private evaluator access -> `hard_evidence` plus `MANUAL_PRIVATE_EVIDENCE`;
- owner publication/egress decision -> `external_authority` plus `OWNER_DECISION`;
- billable run authorization -> `external_authority` plus `PAID_COMPUTE_AUTHORITY`;
- repository-side preparatory implementation -> ordinary `hard_merge`/`soft_preferred` as appropriate.

Completion of the preparatory code edge must not satisfy the external/evidence edge.

## Existing Veritas examples

### Issue #32 — first paid SRE pilot manual gates

Repository/scientific/rehearsal gates are already recorded separately from the remaining seller and
payment work. The remaining items classify as:

- finalize legal/contracting seller name and billing contact -> `LEGAL/COMMERCIAL_AUTHORITY` +
  `OWNER_DECISION`;
- activate payment rail/account -> `EXTERNAL_ACCOUNT` + `LEGAL/COMMERCIAL_AUTHORITY`;
- complete private SOW/invoice fields and tax/withholding review ->
  `LEGAL/COMMERCIAL_AUTHORITY` + `OWNER_DECISION`.

These are go-to-market prerequisites for taking payment, not reasons to block unrelated engineering,
and not evidence that the SRE benchmark is scientifically qualified.

### Issue #71 — HUD/DataVendor and Prime distribution

The repository-side packages are preparation; the remaining account-native steps are external work:

- vendor/Hub account creation, login, onboarding, tier access -> `EXTERNAL_ACCOUNT`;
- HUD NDA, priced offers, contractual/platform commitments -> `LEGAL/COMMERCIAL_AUTHORITY` +
  `OWNER_DECISION`;
- private/public publication choice and any external-private-data egress -> `OWNER_DECISION`;
- Hosted Evaluation or provider runs -> `EXTERNAL_ACCOUNT`, and additionally
  `PAID_COMPUTE_AUTHORITY` whenever the run can consume unauthorized billable resources;
- buyer-safe account-native listing/environment/run IDs -> evidence that the external distribution
  action occurred, not scientific or Frontier qualification.

A repository PR cannot close #71 merely because adapters or packages install successfully.

### Frontier Qualification — issues #63 / PR #65

Frontier Qualification itself is an evidence/qualification program, not an external-account class.
Its authority boundaries are narrower and explicit:

- access to the frozen private evaluator, decryption material, or private-side aggregate evidence ->
  `MANUAL_PRIVATE_EVIDENCE`;
- deliberate non-local egress of private benchmark material -> `OWNER_DECISION` in addition to the
  applicable private-data/provider policy;
- paid frontier/model runs, if later required and not covered by an approved budget/credit ->
  `PAID_COMPUTE_AUTHORITY` plus any required `EXTERNAL_ACCOUNT` access.

Missing strong-agent evidence remains UNKNOWN/NOT_YET_FRONTIER_QUALIFIED. Account access, recovered
keys, or authorization to spend do not themselves make a Frontier gate PASS.

## Evidence and audit requirements

For an authority requirement to move from PENDING to SATISFIED, record only the minimum buyer-safe
facts needed to reconstruct the decision:

- authority class;
- issue/work ID;
- actor or authority role where disclosure is appropriate;
- timestamp;
- non-secret external acknowledgement/decision/evidence reference;
- exact scope or budget authorized where applicable;
- any expiration/revocation condition;
- which dependency was satisfied.

Never record passwords, access tokens, API keys, private keys, raw private benchmark rows, protected
customer data, or secret-bearing command output in roadmap comments or manifests.

If the evidence cannot be recorded safely, record an opaque private evidence reference and keep the
sensitive material in its approved private system.

## Completion semantics

Authority work is DONE when the authority action/evidence required by that ticket has actually been
completed or when an explicit owner decision records a legitimate terminal disposition such as defer
or not-planned under the ticket's completion rule.

It is not DONE merely because:

- preparatory code merged;
- CI is green;
- an email was sent;
- an account could theoretically be created;
- a scientific or Frontier report passed;
- a draft contract/invoice/listing exists;
- a free substitute run completed when the requirement calls for account-native/private evidence.

Negative outcomes can still complete the work when the work class is an experiment or explicit
decision and the required evidence/disposition has been recorded.

## Falsifiers

The policy is violated if any of the following is possible:

- a normal roadmap claim is treated as permission to create an account, accept terms, spend money, or
  use private credentials;
- authority-only work appears as ordinary READY implementation work without a bounded preparation
  scope;
- manual/private evidence disappears from dependency tracking because it is not code;
- a merged preparation PR automatically satisfies an external/manual dependency;
- seller/account setup is presented as scientific, Frontier, training, or verifier qualification;
- authorization to run paid compute is treated as successful experiment evidence;
- secret/private payloads are copied into roadmap metadata to prove completion;
- a silent or unavailable owner is treated as approving an OWNER_DECISION action.

## Automation boundary

The current claim workflow is the enforcement target for this policy, but this ticket owns only roadmap
documentation/metadata semantics. Workflow implementation must occur in its owning coordination lane.

Until the claim workflow understands the authority metadata directly, issue authors and roadmap
synchronizers must fail closed: authority-only work is not labeled ordinary `work:ready`, and any
agent-preparation exception must be explicitly scoped in the Work Contract.

A future automation change satisfies this policy only if it rejects normal `/claim` for pending
authority-only work while still allowing an explicitly declared preparation subtask without granting
any account/private/paid/legal/owner authority.

## Evidence boundary

This document classifies coordination authority only. It does not satisfy any external/manual gate,
authorize spending or account actions, expose private evidence, change qualification state, or grant
merge/release authority.
