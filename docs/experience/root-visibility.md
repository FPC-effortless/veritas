# MachineExperience safe-export visibility

`public_payload()` and `buyer_safe_payload()` respect the experience root's
classification as well as every nested classification. There is no implicit
root declassification operation.

| Root classification | Public export | Buyer-safe export |
| --- | --- | --- |
| PUBLIC | allowed | allowed |
| BUYER_SAFE | refused | allowed |
| INTERNAL | refused | refused |
| EVALUATOR_PRIVATE | refused | refused |
| SEALED | refused | refused |

A refused root raises the existing `ValueError` before traversal. Allowed roots
still delegate trajectory export to its own safe exporter; a more-private nested
trajectory therefore refuses rather than being relabeled. More-private annotation
references are omitted and private metadata/payload buckets remain omitted.
The original object, identity, readiness, maturity and classification are unchanged.

This closes the historical root-only exception to the visibility walk described
in the canonical ontology audit (§ privacy). Compatibility intentionally tightens:
callers that previously projected an INTERNAL or more-private experience through
these safe APIs must now retain it privately or obtain a separately authorized,
properly classified artifact. Do not merely relabel the original to bypass refusal.

`model_dump()`/`model_dump_json()` are unrestricted storage/transport serialization,
not public or buyer-safe export APIs. This boundary does not prevent a caller
from explicitly discarding classifications or copying data through arbitrary code.
No automatic declassification or general information-flow guarantee is claimed.

The dedicated root-visibility tests use only ordinary public synthetic fixtures.
They exercise all root/trajectory audience combinations, nested reference filtering,
private bucket omission, unchanged identity and input immutability.
