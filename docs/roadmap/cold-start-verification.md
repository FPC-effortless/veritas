# Roadmap cold-start verification

Status: `PASS` for repository/GitHub-only discovery, collision inspection, and
claim acquisition. This is coordination evidence only; it grants no merge,
release, qualification, sealed/private-data, paid-compute, deployment,
external-account, or commercial authority.

Owning work: `ROADMAP-BOOTSTRAP-VERIFY-001` / [#243](https://github.com/FPC-effortless/veritas/issues/243)

## Test boundary

This run began from only the public repository URL. It used the checked-out
repository and live GitHub issue, pull-request, comment, label, branch, and
reservation state. It did not use prior Veritas conversation history to choose
the work item or reconstruct ownership.

The observable outcome was a fresh agent finding the coordination entrypoint,
identifying every live READY candidate, rejecting conflicting or authority-bound
work, and receiving an accepted claim on a disjoint lane. The run would fail if
the agent needed hidden context, selected a non-READY item, could not determine
dependencies or ownership, or acquired an overlapping reservation.

## Entry point and queue reconstruction

The repository-native startup path was sufficient:

1. `AGENTS.md`, `.agents/veritas/OVERLAY.md`, and
   `.agents/universal/CONTRACT.md` define the mandatory work loop and hard
   boundaries.
2. `docs/roadmap/work-discovery.md` supplies the exact READY query and declares
   trusted bot status—not labels or the checked-in manifest snapshot—as execution
   authority.
3. [Coordination root #150](https://github.com/FPC-effortless/veritas/issues/150)
   exposes the live global reservation record.
4. The live query
   `is:issue is:open label:agent-work label:work:ready` returned exactly
   [#213](https://github.com/FPC-effortless/veritas/issues/213) and
   [#243](https://github.com/FPC-effortless/veritas/issues/243) before the claim.

`ROADMAP-TEST-001` / #213 is a valid allow-listed no-source coordination
rehearsal. `ROADMAP-BOOTSTRAP-VERIFY-001` / #243 is the work whose acceptance
criteria exactly match this cold-start run and declares one concrete writable
path, so #243 was the appropriate selection.

After the accepted claim, the same READY query returns only #213. This is the
expected discovery-state change; the trusted status and reservation registry
below remain the authority.

## Dependency proof for the selected lane

The issue body still records its historical initial `BLOCKED` state, so the run
did not treat that mutable prose or the `work:ready` label as authority. The
latest trusted [status record](https://github.com/FPC-effortless/veritas/issues/243#issuecomment-5461171896)
contained the bot-authored dependency-ready event for canonical `main`
`7452f515a3835a354bab7cad67c8b51f39a655f4` and established unowned `READY`
before the claim.

| Dependency | Trusted completion evidence |
| --- | --- |
| `COORD-001` / #151 | [`DONE`](https://github.com/FPC-effortless/veritas/issues/151#issuecomment-5450865848), recovered against exact merged PR #246 head `291b8c1100f26236cad3920cf1b45c2a5a8933d0` |
| `ROADMAP-002` / #196 | [`DONE`](https://github.com/FPC-effortless/veritas/issues/196#issuecomment-5454943403), linked to PR #262 head `9eab592bd907b0b8f546436b494c82afde4b24c5` |
| `AGENT-DISCOVERY-001` / #208 | [`DONE`](https://github.com/FPC-effortless/veritas/issues/208#issuecomment-5461176620), linked to merged PR #296 head `ba6e7e65697023a58cdccc26cb4e0fd861534f1c` |
| `ROADMAP-CLAIM-BOOTSTRAP` / #216 | [`DONE`](https://github.com/FPC-effortless/veritas/issues/216#issuecomment-5461175427), bound to owner evidence class `COORDINATION_OPERATION` |

The working branch was created from then-current `main`
`55812db400bb7614500e9b3e5607a15acf7986b7`, rather than from the older
dependency-reconciliation base or an unrelated feature branch.

## Active and open-PR boundaries

The live trusted [reservation registry](https://github.com/FPC-effortless/veritas/issues/150#issuecomment-5461171069)
at `2026-08-31T10:10:52.954Z` contained 21 entries: 4 holder-retained
`BLOCKED`, 14 `REVIEW`, and 3 `CLAIMED`. The selected path was absent before
claim and appears afterward only under #243.

The legacy/open lanes named by the Work Contract were reconstructed as follows:

| PR | Live boundary observed | Collision consequence |
| --- | --- | --- |
| [#134](https://github.com/FPC-effortless/veritas/pull/134) | Open; `MIG-001` / #184 is `REVIEW` with three frozen structured-corpus paths | Explicit active reservation; do not edit its docs, source, or test paths |
| [#147](https://github.com/FPC-effortless/veritas/pull/147) | Open; `DATA-001` / #185 is `REVIEW` with seven frozen Gold-10 acquisition paths | Explicit active reservation; do not edit its workflow, data, docs, source, or tests |
| [#149](https://github.com/FPC-effortless/veritas/pull/149) | Merged; no active registry entry | Historical boundary is integrated, not a free-standing active claim |
| [#65](https://github.com/FPC-effortless/veritas/pull/65) | Open draft with 30 changed Frontier paths | Its changed files remain live claim-time reservations even without an agent-work entry |
| [#118](https://github.com/FPC-effortless/veritas/pull/118) | Open with 23 changed public-investigation paths | Its changed files remain live claim-time reservations even without an agent-work entry |

None of these frozen or open-PR changed paths equals or contains
`docs/roadmap/cold-start-verification.md`, and the coordinator independently
confirmed that conclusion by accepting the claim and atomically adding its
reservation.

Collision rejection is also directly visible in the production rehearsal: a
competing claim on #213 was
[rejected](https://github.com/FPC-effortless/veritas/issues/213#issuecomment-5466954009)
with the current holder named. This proves that a second claimant does not
silently share an active lane; the final trusted #213 status returned to
unowned `READY` at transition 29.

## Claim outcome

The exact command was:

```text
/claim codex-cold-start-a1 audit/roadmap-cold-start
```

The coordinator accepted it at `2026-08-31T10:10:42.309Z`. The trusted #243
record now states:

- state: `CLAIMED`;
- authenticated GitHub actor: `FPC-effortless`;
- agent: `codex-cold-start-a1`;
- branch: `audit/roadmap-cold-start`;
- frozen ownership: `docs/roadmap/cold-start-verification.md`;
- linked PR/head: unset until handoff;
- transition sequence: 2.

This is a positive end-to-end result for cold-start pickup: the repository and
GitHub state alone identified a safe item, exposed competing reservations and
collision behavior, supplied a concrete branch and write boundary, and produced
an auditable accepted claim without hidden coordination.

## Remaining lifecycle

The claim authorizes only this document on the claimed branch. Completion still
requires a PR that references #243 and `ROADMAP-BOOTSTRAP-VERIFY-001`, exact-head
handoff, applicable CI/security checks, and merge-authoritative approval from a
GitHub identity different from the PR author. Head movement invalidates prior
exact-head handoff and review evidence.
