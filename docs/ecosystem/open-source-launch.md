# Veritas-led open-source launch worklist

The public code is already Apache-2.0. The launch goal is independent adoption of
a reproducible assurance workflow, with Veritas as the commercial entry point,
Forge/TrainLab independently usable and Research Lab OS explicitly experimental.
The market assessment motivating this work is a strategy hypothesis, not fresh
competitor research or evidence of demand for this project.

## Outcome contract for this increment

Add a discoverable ecosystem entry point, contributor/security/governance guidance,
complete component license packaging, a built-wheel clean-install check and one
account-free comparison linking all four components through the existing shared
evidence envelope. Preserve directory/import history and Apache licensing. Reuse
existing pilot, source, verifier, review and release contracts. Do not provision
services, publish packages, contact customers or promote scientific claims.

The falsifiers are clean-environment install/CLI tests, source/fixture/artifact/
metadata tampering, constructed verifier controls and direct recomputation of
both agent results. Passing these is implementation evidence only.

## Evidence-based status

| Work | State / next evidence |
| --- | --- |
| Public framework license and private-asset boundary | Existing root Apache-2.0 + LICENSING.md; preserved |
| Standalone component distributions | Existing packages; Forge/Research Lab now include the full root Apache text in distribution artifacts |
| Overview, contributing, governance, security route | Added in this increment; private-reporting availability still depends on repository admin configuration |
| Public end-to-end quickstart | Constructed scripted-policy comparison implemented; no new trained-model capability claimed |
| Clean-install and compatibility checks | Runnable workflow/tooling provided; record actual local/CI executions separately |
| Credential/history disclosure audit | Read-only redacted scan completed for locally available Git refs; six generic candidates inspected as checksums/fixture status, with no confirmed credentials among those findings. This is not a private-benchmark or legal-ownership audit |
| Copyright/source rights/dependency licenses | Root/component notices retained; full legal ownership and every third-party source permission are not attested |
| Independent external user replication | NOT_PERFORMED; code tests and same-host replay do not substitute for another developer |
| Head-to-head competitive/productivity proof | NOT_PERFORMED; no claim to outperform HUD, Harbor, MLflow, DVC or Ray |
| Useful trained-model improvement surviving independent held-out scoring | NOT_DEMONSTRATED by this scripted fixture; requires authorized models/data and separate reviewed experiment |
| CPU image vulnerability remediation | The [current PyTorch runtime](../../integrations/trainlab/PYTORCH.md) passed its recorded scan and CPU checks; CUDA remains unverified |
| Package publication / public launch / production rollout | NOT_AUTHORIZED by these changes; existing release, fresh image-security and operator-acceptance gates remain binding |
| Design-partner conversations / paid pilots / repeat purchase | NOT_VALIDATED; use the existing commercial inquiry and pilot material |

Do not reset the existing [paid-pilot launch checklist](../commercial/launch-checklist.md)
to “0/12”: it already records completed release and qualification work, as well as
seller-controlled legal/payment and customer-specific delivery blockers. Neither
this source work nor market-category activity proves new customer demand.

## Three proofs to earn

1. An external developer installs the published permitted inputs/code, executes a
   frozen protocol and reproduces the declared scores within preregistered bounds.
2. A reviewed scientific exercise catches leakage, altered model/data identity,
   broken verifier behavior and unfair comparisons while preserving negative and
   unknown outcomes. The quickstart supplies bounded software falsifiers only.
3. A failure diagnosed by Veritas leads to a controlled model/training intervention
   through Forge/TrainLab, and the improvement survives independent replication
   and untouched held-out evaluation. Declare data, weights, seeds, budgets,
   alternatives, stopping rules, uncertainty and limits before running it.

Use established execution/training/tracking platforms for these proofs rather
than treating a broader feature catalog as defensibility. Paid Veritas evaluation,
private environment maintenance and customer integration/support can be tested
without financing a general GPU cloud or changing Apache rights.

## Proposed commercial decision gates

Use **10–15 qualified customer conversations, two paid evaluation pilots and one
repeat engagement** as proposed learning gates, not forecasts or completed sales.
Record the buyer's actual deployment decision, alternatives, expected value,
what evidence changed the decision and whether they would pay again. Keep names,
pricing, contracts and private notes outside the public repository. Several
external developers completing the workflow without direct maintainer assistance
would be adoption evidence; stars alone are not.

Existing [pilot scope](../commercial/pilot.md), [onboarding](../commercial/onboarding.md),
[acceptance](../commercial/evaluation-acceptance.md), SOW and commercial inquiry
form remain the starting materials. This work initiates no outreach, promises no
SLA and authorizes no payment collection or redistribution of private assets.

## Local implementation evidence — 2026-11-02

On Python 3.12.14, the four component wheels installed into an isolated virtual
environment and imported only from that installation. All four distributions
contained the complete root Apache license text. The constructed comparison
executed both scripted policies and reverified their 1.0/0.0 scores with
`NOT_PROMOTED` / `NOT_QUALIFIED`; neither torch nor credentials were required.
All 32 targeted pytest checks passed, including the source/metadata/artifact,
raw-oracle and broken-verifier falsifiers, shared-evidence tests, policies and
release identity. Research Lab (49), TrainLab (49) and Forge (68) checks passed;
the repository quality ratchet introduced no diagnostics. Both container builds
and their existing authentication/restart/backup acceptance passed with Forge
license metadata intact. These checks remain separate from scientific qualification. Hosted Python 3.13 CI and independent external-user
replication are not claimed by a local 3.12 run.

Gitleaks 8.30.1 was checksum-verified and tested on a constructed canary to confirm
full value redaction in reports/logs before scanning all locally available Git
refs. Its six generic-key findings were inspected as one tokenizer SHA256, four
Python-file checksums in historical evidence manifests, and one receipt-fixture
source-kind enum. No credential was tested, no history rewritten and no ignore
rule added. This bounded scan is not a guarantee that every secret format,
private benchmark disclosure, historical Actions artifact, third-party right or
copyright chain has been audited. The full legal/private-data review and
production operator acceptance remain open; every proposed image still needs a
fresh security scan.
