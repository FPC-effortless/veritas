# Security policy

Security reports may involve credentials, private benchmark material or customer
assets. Do not put those details in a public issue, PR, discussion or CI artifact.

## Report privately

If this repository's Security tab offers **Report a vulnerability**, use
[GitHub private vulnerability reporting](https://github.com/FPC-effortless/veritas/security/advisories/new).
Availability is controlled by the repository administrator and is not established
by this document. If that route is unavailable, open a minimal public issue
requesting a private security contact, without exploit details, affected private
assets, tokens or customer information. Exchange details only after a maintainer
establishes a private channel. No unverified email address or response-time SLA
is advertised here.

Include the component, exact source commit and package version, deployment mode,
minimal public/constructed reproduction, impact and proposed mitigation. Keep
actual secret values out of the reproduction. Tell the maintainer privately if a
credential or hidden benchmark was already exposed; do not test credentials
against a live service or republish the exposed material. Coordination precedes
public disclosure of sensitive details.

## Scope and support

Reports about the current development head and the latest published Veritas
release are welcome. Forge, TrainLab and Research Lab OS are incubated packages
with separate version numbers; include theirs as well. An old release or a
passing test does not establish that a particular deployment is supported or
secure. Maintainers assess backports and fixes case by case; no security support
period or enterprise certification is promised.

TrainLab executes trusted operator code and is not a sandbox or multi-tenant
training service. Follow its [production contract](integrations/trainlab/PRODUCTION.md).
Private evaluator state, sealed assets and source-rights controls remain distinct
from local file-integrity checks. See [LICENSING.md](LICENSING.md) and
[private benchmark handling](docs/commercial/private-benchmark-handling.md).

## Validation and deployment limits

The Node dependency audit rejects every reported severity, including development
dependencies. The API and optional PyTorch image workflows reject HIGH/CRITICAL
findings, including unfixed vulnerabilities, and retain complete package
inventories. The API build context allows public package inputs only; local run
stores, credentials and Git data are excluded.

The remediated PyTorch CPU image passed its recorded security and functional
checks; dated evidence and limits are in [the PyTorch guide](integrations/trainlab/PYTORCH.md).
CUDA/NCCL and multi-node qualification still require their own hardware evidence.
These checks do not authorize production deployment or scientific promotion.
Existing release artifacts and running deployments are not replaced by a source
merge: validate each exact image identity. Security and release gates remain
fail-closed; there is no exception merely because a vulnerability has no vendor
fix listed.
