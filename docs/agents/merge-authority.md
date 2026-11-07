# Merge authority for autonomous roadmap agents

**Policy ID:** `veritas.agent-merge-authority.v1`  
**Applies to:** roadmap work coordinated through issue Work Contracts  
**Authority:** subordinate to `AGENTS.md`, repository security/privacy rules, release/qualification contracts, and explicit user/owner instructions

## Purpose

This policy separates three decisions that must not be conflated:

1. **work ownership** — who may edit a lane;
2. **implementation merge authority** — whether an exact reviewed commit may be merged into its target branch;
3. **evidence/qualification/release authority** — whether a scientific, Frontier, training, commercial, private, sealed, external, or release state may be changed.

A roadmap claim grants only the first. It never grants the second or third.

The objective is bounded autonomy: low-risk additive work may merge without another manual click only when the Work Contract explicitly permits that behavior and all exact-head requirements are satisfied. High-authority actions remain manual or evidence-bound.

## Authority order

This document operationalizes, but cannot weaken, the authority order in `AGENTS.md`.

When instructions conflict, apply the stricter applicable rule. In particular:

- explicit user/owner instructions may authorize a merge but do not waive repository security, privacy, qualification, branch-protection, or exact-head requirements;
- a Work Contract may always require stricter/manual authority than this document's default;
- branch protection, rulesets, required reviews, required status checks, environment approvals, and GitHub permissions remain hard controls;
- an automation or agent must never weaken those controls to make a merge possible.

## Core invariants

1. **Claim is not merge authority.** `CLAIMED` only reserves the declared ownership lane.
2. **Handoff is not approval.** `REVIEW` means implementation work was offered for independent review, not that it passed review.
3. **Green CI is not review.** Required checks prove only what they actually test.
4. **Review is exact-head evidence.** Approval applies to the reviewed commit. A material head change requires fresh independent review and rerun of affected gates.
5. **Merge is not qualification.** Landing code cannot silently change scientific, Frontier, training, commercial, or release status.
6. **Missing evidence fails closed.** `UNKNOWN`, absent, skipped, timed-out, or inaccessible evidence never becomes PASS.
7. **Current-main matters.** Work whose semantics depend on shared/current-main state must be synchronized before final verification.
8. **Automation cannot bypass GitHub controls.** No force push, protection/ruleset weakening, check suppression, review dismissal, or equivalent bypass is authorized by roadmap status.
9. **Private/manual authority remains private/manual.** A roadmap claim cannot authorize secret access, sealed evaluation, paid compute, external account actions, legal acceptance, publication, or payment.
10. **Completion state is explicit.** `DONE` may mean merged implementation only when the Work Contract's implementation boundary is satisfied; it must not imply unperformed evidence qualification.

## Merge-authority classes

A Work Contract may declare one of these classes. If it declares no class, use the default in the table.

| Class | Typical work | Default implementation merge authority | Extra requirements |
|---|---|---|---|
| `ADDITIVE` | isolated code/docs/tests/adapters in owned paths | `MANUAL` unless the Work Contract explicitly opts into `AUTO_AFTER_REVIEW` | exact-head required gates + independent review |
| `SHARED_CONVERGENCE` | root exports, shared package metadata, shared workflows, cross-lane convergence | `MANUAL` unless explicitly authorized | sync to current `main`, inspect provider dependencies, full applicable suite, independent exact-head review |
| `QUALIFICATION_IMPLEMENTATION` | code implementing scientific/Frontier/training qualification machinery | implementation may follow `ADDITIVE` or `SHARED_CONVERGENCE`; qualification state does not | evidence gates remain separate and fail closed |
| `EVIDENCE_DECISION` | writing/changing scientific, Frontier, training, commercial qualification results or authoritative evidence status | never roadmap-auto-merged merely from CI/review | exact evidence contract + designated evidence authority |
| `MANUAL_PRIVATE_EXTERNAL` | private/sealed data, paid/manual model runs, external accounts, secrets, vendor consoles | never roadmap-auto-dispatched or auto-merged merely from a claim | explicit authorized operator/action boundary |
| `RELEASE_PUBLISH_LEGAL` | releases, publishing, payments, licensing/legal acceptance, production promotion | never roadmap-auto-merged/published by default | explicit owner/release/legal/payment authority and applicable release gates |
| `SECURITY_GOVERNANCE` | branch protection, rulesets, permissions, secret policy, authority policy enforcement | manual unless an explicit higher-authority contract says otherwise | security review; no protection weakening |

`AUTO_AFTER_REVIEW` is an opt-in capability, not the default meaning of `READY`, `CLAIMED`, or `REVIEW`.

## Required Work Contract declaration

For new or updated roadmap tickets, use an explicit field when autonomous merge is desired:

```text
Merge authority: AUTO_AFTER_REVIEW | MANUAL | OWNER | EVIDENCE_AUTHORITY
```

Semantics:

- `AUTO_AFTER_REVIEW` — an authorized agent may merge only after this policy's pre-merge predicate is satisfied.
- `MANUAL` — a person or separately authorized merge action must perform the merge after gates/review.
- `OWNER` — explicit repository/product owner authorization is required for the exact candidate.
- `EVIDENCE_AUTHORITY` — the action changes an evidence/qualification state and requires the authority named by the applicable scientific/release contract.

If the field is absent, the default is **`MANUAL`**. This preserves compatibility with existing tickets and prevents old claims from acquiring new merge powers retroactively.

A higher-level explicit user instruction such as “merge PR #123” can provide the manual/owner merge action for that request, but it does not waive exact-head checks, independent review, privacy/security boundaries, or evidence-specific authority.

## Independent-review requirement

An implementation agent must not self-approve its own implementation as the independent reviewer.

An independent review is acceptable only when it:

- identifies the exact commit reviewed;
- examines the changed semantics and relevant falsifiers, not only CI status;
- has no unresolved blocking finding;
- is performed by a reviewer independent of the implementation path under the active Work Contract;
- is recorded in a durable repository surface such as the PR review/conversation or linked evidence record.

A generic approval made before the final implementation head is insufficient unless the reviewer explicitly confirms that the later head is unchanged-equivalent under the repository's review policy. When in doubt, require fresh review.

## Exact-head gate predicate

Before an authorized agent merges an `AUTO_AFTER_REVIEW` implementation, all of the following must be true at the same candidate head:

1. the PR is open, non-draft, and targets the intended branch;
2. the head still belongs to the claimed Work Contract lane;
3. the final changed-file set respects positive and negative ownership;
4. declared dependencies are merged or otherwise satisfied exactly as the Work Contract requires;
5. the candidate is mergeable without bypassing branch controls;
6. every required/applicable implementation gate has actually completed successfully on the final head or its GitHub synthetic merge commit, according to the workflow's contract;
7. skipped/non-applicable gates are justified by their actual workflow trigger or Work Contract, not assumed;
8. independent review covers the exact final head and has no unresolved blocker;
9. no newer review comment, issue blocker, security finding, or dependency change invalidates the approval;
10. `main`/target-branch movement has been evaluated under the task class below;
11. no private/sealed/manual/paid/external/release/evidence authority is being inferred from the merge;
12. the merge method itself is permitted by repository rules.

If any predicate is unknown, the agent must not auto-merge.

## Target-branch movement

### Ordinary additive work

If the target branch advances after final review/gates, the agent must determine whether the PR's final merge candidate has been re-evaluated by GitHub against the new target.

Auto-merge is allowed only when:

- the PR remains mergeable;
- required checks that are defined on the synthetic merge candidate have rerun successfully against the new target where repository configuration requires that;
- there is no dependency or semantic conflict introduced by target movement;
- the independent review remains applicable to the unchanged implementation diff.

If target movement changes the implementation head, generated artifacts, dependency semantics, or reviewed diff, require fresh review.

### Shared convergence/root integration

`SHARED_CONVERGENCE` must synchronize onto the current target branch before final verification. After synchronization:

- rerun the full applicable repository suite and shared-surface checks;
- recheck provider/consumer dependency ordering;
- perform independent review of the synchronized exact head;
- do not rely on an approval of a pre-sync commit.

This stricter rule applies to root exports, shared package metadata, shared workflows, compatibility convergence, and similar serialized integration work.

## Gate scope

Use the verification ladder in `docs/agents/verification.md`.

An agent must report only gates that actually ran. Examples:

- a docs-only change may legitimately not trigger Python Quality when the workflow path filter excludes docs;
- a Python/runtime change that triggers CI, Security, and Python Quality must not call itself green while one is missing or still running;
- a portability change may require portability-specific conformance gates in addition to generic CI;
- a scientific qualification decision may require replicated/model/manual evidence that ordinary CI cannot provide.

A missing required workflow is a blocker until its non-applicability is established from the active workflow/Work Contract or an authorized dispatch is used where repository policy permits.

The authorized-dispatch workflow may run allow-listed validation workflows on `main`; its acknowledgement is not merge or qualification authority.

## Scientific, Frontier, and training work

Code that implements qualification machinery may be merged as implementation work if its implementation merge class permits it. The following remain separate:

- verifier/environment scientific qualification;
- Frontier qualification;
- training-value qualification;
- learning-efficiency claims;
- commercial qualification.

A merged implementation can therefore be `DONE` at the code-delivery boundary while the corresponding evidence state remains `UNKNOWN`, `NOT_QUALIFIED`, `NOT_YET_FRONTIER_QUALIFIED`, or another contract-defined non-PASS state.

An agent must not auto-merge a change whose purpose is to declare or promote an authoritative qualification result unless the applicable contract explicitly identifies the evidence authority and that authority has approved the exact evidence candidate.

Green tests that validate the qualification *software* are not evidence that a model, environment, benchmark, or training run passed qualification.

## Manual, private, sealed, paid, and external work

The following actions are outside ordinary roadmap auto-merge/dispatch authority unless an explicit higher-authority instruction grants the specific action:

- decrypting, opening, materializing, exporting, or publishing sealed/private benchmark material;
- running manual or expensive model calibration/training/Frontier workflows when policy marks them controlled;
- creating or using external vendor/customer accounts;
- accepting terms, NDAs, licenses, legal agreements, or marketplace conditions;
- spending money, purchasing compute, creating paid resources, or changing billing;
- publishing a benchmark/environment/model/package to an external hub or marketplace;
- sending customer/vendor communications that constitute an external commitment;
- changing secrets, credentials, access control, branch protection, or repository rulesets.

A code/document PR that prepares such a workflow may still merge under its own implementation class. Executing the external/manual action is a separate authority boundary.

## Release, publish, payment, and legal authority

Release code and release execution are distinct.

An agent may implement or repair release tooling under a properly scoped Work Contract, but must not infer permission to:

- cut/tag a release;
- publish artifacts/images/packages;
- promote production;
- sign or accept legal terms;
- make a payment or paid purchase;
- declare external distribution complete.

Those actions require the explicit authority defined by the release/commercial/legal contract and all exact release-candidate evidence. `BUILD_STATUS.md` and the active release workflow remain release-state authorities.

## Branch protection and repository controls

Autonomy must operate *inside* repository controls.

Forbidden merge-enablement actions include:

- disabling or weakening branch protection/rulesets;
- changing a required check to optional merely to land the current PR;
- dismissing a blocking review without the authority defined by repository policy;
- force-updating protected refs to bypass review/check requirements;
- modifying quality baselines, exclusions, suppressions, or security configuration solely to hide an introduced defect;
- using a different merge path to evade auditability.

If repository controls prevent an otherwise eligible auto-merge, stop at the authority boundary and record the blocked state. Do not work around the control.

## Completion semantics

Roadmap status must distinguish implementation completion from evidence completion.

### `DONE` is valid for implementation when

- the exact reviewed implementation has merged through an authorized path;
- the Work Contract's implementation acceptance criteria are satisfied;
- any remaining evidence/manual/external work is explicitly outside that ticket's completion boundary or linked to a separate ticket.

### `DONE` must not imply

- scientific PASS;
- Frontier PASS;
- training-value PASS;
- commercial/release readiness;
- completion of an external account/manual action;
- availability of evidence that was not produced.

If the Work Contract combines implementation and evidence/manual requirements, it must remain open/blocked until all required boundaries are satisfied, even if code merged.

## Decision procedure

Before merging, an autonomous agent should answer these questions in order:

1. **What exact action is being authorized?** Merge implementation only, or also evidence/release/external action?
2. **What merge-authority class applies?** If absent, use `MANUAL`.
3. **Does the Work Contract explicitly opt into auto-merge?** If not, stop after handoff/review.
4. **Is the candidate exact head known and ownership-clean?** If not, stop.
5. **Are dependencies and target-branch state current for this class?** If not, sync/revalidate as required.
6. **Did every applicable gate actually pass?** If unknown/missing, stop.
7. **Did an independent reviewer approve the exact final head with no blocker?** If not, stop.
8. **Would the merge cross a scientific/Frontier/training/private/sealed/paid/external/release/legal boundary?** If yes, require the corresponding authority.
9. **Do repository controls permit the merge without weakening them?** If no, stop.
10. **Can completion be recorded without overstating evidence?** If yes, merge implementation only and record the precise post-merge status.

Default answer on ambiguity: **do not auto-merge**.

## Examples

### Eligible only when explicitly opted in

An isolated adapter PR changes only its owned files, depends only on already-merged contracts, has exact-head CI/Security/Quality and adapter-conformance PASS, and receives independent exact-head approval. Its Work Contract says `Merge authority: AUTO_AFTER_REVIEW`. The agent may merge if the PR remains mergeable and no target/dependency change invalidated the evidence.

### Not eligible because authority is absent

The same adapter PR has all green gates and independent approval, but its Work Contract has no merge-authority field. It remains review-ready; an authorized manual/owner merge action is required.

### Shared convergence

A convergence PR edits root exports and package metadata after several provider lanes merge. It must first sync current `main`, rerun the full applicable suite, and receive independent review on the synchronized head. An approval on a pre-sync head does not authorize merge.

### Qualification machinery versus qualification result

A PR adds deterministic training-qualification policy code and tests. The code may merge under its implementation class. The merge does not make any model or environment `TRAINING_VALIDATED`; that requires the separately defined evidence contract and authority.

### Sealed evaluation

A roadmap issue is claimed and the harness code is green. The next step would decrypt a private panel and run a paid Frontier model. The claim and green code do not authorize that step. The agent stops at the manual/private/paid boundary.

### Release

A release-workflow bug fix passes review and merges. Tagging a version, publishing packages/images, or declaring the release complete still requires explicit release authority and exact release-candidate evidence.

## Relationship to coordination commands

- `/claim` changes ownership coordination state only.
- `/handoff` records that implementation is ready for review.
- `/blocked` records a blocker; it does not waive it.
- `/done` may be used only after the Work Contract's completion boundary is actually satisfied.
- none of these commands grants release, sealed, paid-compute, qualification, or legal authority.

Future automation may consume this policy, but automation must fail closed when the Work Contract lacks an explicit auto-merge grant or when required evidence cannot be established.