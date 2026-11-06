# Existing work reconciliation audit

Status: coordination audit only. This file does not grant merge, release, qualification, external-account, private-data, paid-compute, or commercial authority.

Snapshot date: 2026-08-30
Snapshot base: `main` `6682eeb9f69962efd5627ed01d8fa579b6f9004e`
Owning Work ID: `ROADMAP-AUDIT-001` / issue #209

## Purpose

This audit reconciles work that predates the canonical `agent-work` roadmap so a fresh agent does not mistake an old issue or open pull request for unowned work. Live trusted `agent-work` status and the coordinator's live open-PR reservation scan remain execution authority. This document is a durable classification and migration record.

## Classification rules

- `CANONICAL_AGENT_WORK`: represented by an `agent-work` Work ID. Use trusted issue status and its frozen ownership.
- `LEGACY_ACTIVE_RESERVED`: predates the roadmap but an open PR still owns repository paths. It is not claimable through the roadmap until explicitly migrated or superseded.
- `SUPERSEDED`: a newer canonical lane owns the intended capability. Do not restart the older lane.
- `EXTERNAL_MANUAL`: requires third-party, account, legal/commercial, private-evidence, owner-decision, or paid-resource authority. Do not advertise to coding agents as READY.
- `EVIDENCE_ONLY`: retained experiment/reproduction evidence; not a merge lane unless separately re-scoped.
- `SERVICE_CONTROL`: intentionally open operational/control surface, not backlog work.
- `AUTOMATED_DEPENDENCY`: bot-created dependency maintenance. It remains outside `agent-work` until deliberately adopted; its open PR diff is still a live collision surface.
- `DONE_HISTORICAL`: merged/completed historical work; do not recreate it.
- `LEGACY_NONROADMAP_BLOCKED`: unresolved legacy implementation work with no canonical Work ID. It must be migrated into an explicit Work Contract before any coding agent starts.

## Named pre-roadmap reconciliation

| Legacy item | Classification | Canonical mapping / disposition | Coordination consequence |
| --- | --- | --- | --- |
| #32 `launch: complete first paid SRE pilot manual gates` | `EXTERNAL_MANUAL` | Governed by the external/manual authority policy (`ROADMAP-EXT-001` / #214). Remaining work is seller identity, payment rail, SOW/invoice and tax/withholding administration. | Never READY for an ordinary coding agent. Engineering evidence already recorded in #32 does not satisfy the remaining commercial authority. |
| #41 independent CompanyWorld reproduction request | `EXTERNAL_MANUAL` | Third-party independent reproduction request. | Requires an independent external operator; repository ownership/claiming cannot manufacture this evidence. |
| #42 CompanyWorld no-work anchor reconciliation | `LEGACY_NONROADMAP_BLOCKED` | No canonical Work ID was found for this exact baseline-normalization issue at this audit snapshot. | Do not implement directly from #42. First create/migrate a narrow Work Contract with explicit ownership and dependencies; until then it is non-claimable legacy work. |
| #43 Training-value v2 train/heldout diagnosis | `SUPERSEDED` | Superseded by `TRAIN-001` / #162, whose required gates explicitly include train-before/train-after, heldout-before/heldout-after, overfit/memorization checks, parse/reward separation and transfer classification. | Do not reopen #43 as a parallel training lane. Execute the canonical training-qualification program when its dependencies clear. |
| #63 / PR #65 Frontier Qualification | `LEGACY_ACTIVE_RESERVED` plus authority-bound evidence | Draft PR #65 on `feat/frontier-qualification` remains intentionally unmerged. Its declared owned paths are `src/investigation_world/frontier/**`, `tools/frontier_*.py`, `tests/frontier/**`, `.github/workflows/frontier-qualification.yml`, and `docs/frontier/**`. External/private/paid evidence remains separate authority. | Preserve the draft lane and its paths. No roadmap agent may claim overlapping Frontier paths merely because #63 predates `agent-work`. Explicit migration is required before changing its coordination class. |
| #71 HUD/DataVendor + Prime commercial distribution | `EXTERNAL_MANUAL` | Governed by `ROADMAP-EXT-001` / #214. Repository-side preparation is not account-native distribution evidence. | Do not advertise as coding-agent READY. Account onboarding, NDA, listing, hosted evaluation, pricing/publish decisions and any paid-resource action remain external/manual. |
| #106 Veritas automation control | `SERVICE_CONTROL` | Audited command surface for the allow-listed dispatch workflow; intentionally kept open while the bridge is in service. | Not backlog and not claimable work. |
| PR #118 public investigation dataset foundation | `SUPERSEDED` / legacy migration source | The useful structured-corpus portion is explicitly migrated by `MIG-001` / #184 through PR #134. PR #118 remains a legacy Foundry-era branch and is not a fresh claimable lane. | Treat its open diff as reserved until the legacy PR is explicitly closed/superseded; do not patch or revive it opportunistically. |
| PR #134 canonical structured investigation corpus | `CANONICAL_AGENT_WORK` | `MIG-001` / #184, active REVIEW reservation on `feat/investigation-structured-corpus`. | Use trusted #184 status; do not duplicate its three owned files. |
| PR #147 Gold-10 report acquisition runner | `CANONICAL_AGENT_WORK` | `DATA-001` / #185, active REVIEW reservation. | Use trusted #185 status; do not duplicate its acquisition/workflow paths. |
| PR #149 Machine Experience foundation | `DONE_HISTORICAL` | Merged as `6745c7313c13de9ea18d69f62b2585ff8b139f21`; subsequent Machine Experience Work IDs build on it. | Do not recreate as greenfield work. |

## Current open PR reconciliation

An exhaustive `GET /repos/FPC-effortless/veritas/pulls?state=open&per_page=100` snapshot was checked during this audit. Every open PR falls into one of the following buckets.

### Canonical roadmap / trusted reservation lanes

These are already represented by Work IDs and must be interpreted through trusted `agent-work` state, not by PR age or branch freshness alone:

- PR #276 -> `ROADMAP-POLICY-001` / #217.
- PR #281 -> `DEPLOY-001` / #280.
- PR #274 -> `ROADMAP-STATUS-001` / #236.
- PR #260 -> `TRACE-001` / #183.
- PR #273 -> `ROADMAP-EXT-001` / #214.
- PR #263 -> `SANDBOX-001` / #174.
- PR #270 -> `TRACE-002` / #154.
- PR #278 -> `ROADMAP-003` / #197.
- PR #279 -> `ROADMAP-PRIORITY-001` / #234.
- PR #266 -> `ROADMAP-AGENT-ID-001` / #222.
- PR #265 -> `ROADMAP-MERGE-001` / #229.
- PR #267 -> `ROADMAP-BRANCH-001` / #226.
- PR #264 -> `COMP-001` / #182.
- PR #258 -> `DATA-002` / #186.
- PR #134 -> `MIG-001` / #184.
- PR #147 -> `DATA-001` / #185.

The coordinator's global reservation registry is the live ownership source for these active lanes.

### Legacy active or evidence-only PRs

- PR #65 Frontier Qualification: `LEGACY_ACTIVE_RESERVED`; draft and explicitly not mergeable without deliberate authority. Preserve its Frontier path reservation.
- PR #118 public investigation dataset foundation: `SUPERSEDED` migration source; structured-corpus capability moved to PR #134. Do not treat #118 as READY.
- PR #73 DataVendor listing documentation: legacy commercial preparation associated with #71; repository preparation does not satisfy external account/listing authority. Treat its open diff as reserved until explicitly resolved.
- PR #109 corrected Hugging Face benchmark V2: `EVIDENCE_ONLY`; its body explicitly says it is not intended to merge.
- PR #107 first Hugging Face benchmark: `EVIDENCE_ONLY` and superseded experimentally by #109 after the first transport prompt was falsified. Do not merge/restart it.
- PR #28 Foundry transfer-training experiment: `EVIDENCE_ONLY` / legacy training experiment; future training-value claims belong under `TRAIN-001` / #162 rather than an ad-hoc merge lane.
- PR #25 bounded 3B+ CompanyWorld calibration profile: `EVIDENCE_ONLY` legacy calibration screen; not an autonomous permanent-work lane.

### Automated dependency PRs

Open Dependabot-style dependency PRs #2, #3, #4, #5 and #6 are `AUTOMATED_DEPENDENCY`. They are not `agent-work` and must not be silently adopted by a coding agent. Their open changed files remain collision-relevant. Integration requires the repository's normal dependency/security/review policy.

## Duplicate and supersession rules

1. #43 must not run in parallel with `TRAIN-001` / #162; the canonical ticket subsumes the diagnostic requirements.
2. PR #107 is superseded as a capability-ranking experiment by corrected PR #109; retain #107 only as harness-falsification evidence.
3. PR #118 must not be treated as a fresh Foundry implementation lane. PR #134 is the canonical structured-corpus migration. Any remaining useful #118 capability requires an explicit new migration Work ID before implementation.
4. PR #149 is completed foundation work and must not be recreated.
5. Legacy/open PRs that are not canonical `agent-work` remain protected by open-PR changed-file reservations until explicitly closed, migrated or superseded.

## Manual and external authority separation

The following must never be converted to coding-agent READY merely because repository preparation exists:

- #32 seller/payment/legal administration;
- #41 independent third-party reproduction;
- #71 HUD/DataVendor/Prime account-native distribution;
- private evaluator/decryption or deliberate private-data egress associated with #63/#65;
- paid strong-model runs or other billable resources without explicit authority.

No secret, private row, hidden label, decrypted benchmark content, credential, or account token belongs in roadmap metadata.

## Active ownership reconstruction rule

A fresh agent must use both sources before selecting work:

1. trusted `agent-work` status / global reservations for canonical Work IDs; and
2. live open-PR changed-file reservations for legacy or automated PRs.

An old issue being unlabeled or absent from `.github/agent-roadmap.yml` is never evidence that its open PR paths are free.

## Acceptance result for ROADMAP-AUDIT-001

At this snapshot:

- every named pre-roadmap item from #209 has an explicit canonical, legacy, external/manual, service-control, superseded, evidence-only, or DONE classification;
- #118 is explicitly migration/supersession, not a fresh claimable lane;
- PR #65 Frontier ownership remains protected while draft;
- #32/#41/#71 and private/paid Frontier actions are excluded from autonomous READY work;
- the exhaustive open-PR snapshot is partitioned into canonical trusted reservations, protected legacy/evidence lanes, or automated dependency maintenance;
- unresolved #42 is explicitly fail-closed as `LEGACY_NONROADMAP_BLOCKED` until a Work Contract is created, rather than being silently available.

Falsifier: if a fresh agent can identify an open PR whose changed paths are absent from both trusted reservations and the live open-PR collision scan, or can start #42/#32/#41/#71 as ordinary READY work without an explicit new authority/migration event, this audit is not sufficient and must be reopened.
