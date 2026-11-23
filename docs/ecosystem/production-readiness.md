# Operating Veritas in production

This guide defines the supported operating boundaries and the evidence needed to
promote a reviewed installation. Production readiness belongs to an exact source,
runtime, configuration and host. A successful research result or package build
does not establish those operating facts.

## Supported surfaces

| Surface | Supported use | Deployment contract |
| --- | --- | --- |
| TrainLab and Forge workbench | One private workspace, trusted operators and approved recipes, durable local stores | [TrainLab production contract](../../integrations/trainlab/PRODUCTION.md) and [Forge workbench](../../integrations/forge/WORKBENCH.md) |
| Research Lab observatory | Authenticated, read-only view over research records; execution remains with the existing bounded supervisor and operator CLI | [Authenticated hosting](../../integrations/research_lab/README.md#authenticated-observatory-hosting) and [supervisor/recovery](../../integrations/research_lab/AUTONOMY.md) |
| Latent diagnostics | Frozen plans, declared optional runtime, bounded numerical work, private verified exports and exact saved-output replay | [Latent research](latent-research.md) and [validation scope](latent-validation.md) |
| Episode API in the root container | One process with bounded, ephemeral episode sessions and a separate privileged orchestration API | [Episode API operations](../production-episode-api.md) |
| Website | Built Next.js frontend; the research services have their own explicit deployment contracts | Root package build and CI |

The workbench uses a shared trusted-operator account. Research recipes execute as
the service account. This deployment boundary does not provide tenant isolation
or isolation for hostile submitted code. The episode API's session state is
ephemeral; export its trajectory before deleting the session or restarting it.
Persistent research evidence belongs in the existing run and research stores.

## Reliability requirements enforced in code

### Rejected research remains recoverable

An inadequately specified experiment can be a correct refusal. TrainLab health
counts `adequacy-refusals` separately from executed runs, and offline backup/restore
preserves their original bytes and `UNKNOWN`/`INADEQUATE` status. Malformed or
unknown store entries still fail validation. The run store and refusal store each
have explicit record and aggregate metadata ceilings. Health and dashboard reads
must agree on these capacity limits.

Backups retain finalized runs and refusal evidence only. Forge datasets, research
database/snapshots, approved recipes, credentials and runtime dependencies require
their separately documented backup and recovery procedures. Restore to a new
directory and reverify before replacing the working store.

### Health detects the service it represents

The authenticated research observatory checks run storage, an enabled Forge
workspace, and its existing SQLite database. A damaged database, missing required
schema or exhausted probe budget returns 503. Health responses expose aggregate
state without research names, data rows or paths. The probe does not recreate a
missing database and does not assert worker liveness or scientific validity.
Production startup also refuses an uninitialized or unhealthy research root before
controller initialization; a missing volume cannot silently become an empty lab.

Worker liveness has its own supervisor health check. The episode API separates
process liveness (`/healthz`) from readiness to accept privileged orchestration
(`/readyz`). Alerting must use the relevant endpoint and retain the distinction.

### Evidence export cannot look successful after failure

Latent ZIP export stages a private archive, streams file capture and verification,
checks the captured manifest and file hashes, then publishes without overwriting
an existing destination. Capture or verification failure leaves no final export.
An error after publication, such as a directory-fsync failure, can leave the verified
archive present with uncertain filesystem durability. File count and byte
limits are checked before publication. POSIX exports retain mode 0600; copying
them elsewhere remains an operator-controlled disclosure decision.

CSV exports neutralize formula-leading text while preserving numerical values.
Numerical diagnostics reject excessive dense-workspace and draw counts before
their expensive allocations. These calculations bound known work; actual process
memory, library workspaces, callback code and total disk use also need OS/container
limits and monitoring.

### Episode sessions have a defined lifetime

The API bounds request bodies, URL/search input, generated-task count, per-session
budgets and simultaneous sessions. Session access, deletion, idle expiry and
shutdown coordinate cleanup so a removed session cannot keep using a closed
database. The root container runs one worker and limits transport concurrency.
Canonical world validation remains enforced under optimized Python too.

### Release publication requires source-bound evidence

`tools/verify_release_gates.py` checks the checkout, main ancestry and canonical
tag target, then requires successful exact-source CI and Security evidence. It
rejects missing, skipped, failed, stale or malformed evidence and checks the latest
attempt's required jobs. A workflow on a research branch cannot stand in for the
main/tag release check.

The release workflow builds and boots one candidate image, captures its Docker
ImageID, scans that image, and converts the same scan report into its CycloneDX
inventory. It validates image/source/scan/inventory identity before tagging and
pushing that captured image without rebuilding. The published registry manifest's
config digest must match the scanned ImageID before provenance is emitted. Ordinary
CI exercises this inventory-validation path without registry publication.

Source checks run before publishing the image and again before publishing GitHub
release assets. The release manifest binds the image evidence, gate receipt's hash
and workflow identities. Ordinary validation jobs have read-only permissions;
publication permissions remain scoped to the publish job. Existing release identity,
licensing, privacy, scientific and external-runtime gates continue to apply.

## Verification before an installation is promoted

Use the exact reviewed revision and save the command results with its identity.
The repository workflows execute the appropriate checks on supported Python
versions. Useful local checks from an installed checkout include:

```bash
python -m pytest
python -m unittest discover -s integrations/trainlab/tests -v
python -m unittest discover -s integrations/forge/tests -v
python -m unittest discover -s integrations/research_lab/tests -v
python -m unittest discover -s integrations/trainlab/tests_latent -v
python -O -m unittest discover -s integrations/trainlab/tests_latent -v
python tools/quality_baseline.py check
```

Install the declared optional test/runtime dependencies before claiming their
checks passed. In particular, the actual authenticated HTTP regression needs the
hash-pinned Waitress runtime; native diagnostics need their approved framework;
browser checks need Playwright and Chromium. An unavailable optional component is
unverified, not a passing compatibility result. When executing copied recipes from
source, use absolute `PYTHONPATH` entries because the runner changes working
directory; a clean wheel installation avoids that dependency on the checkout.

The CI paths cover package installation, constructed ecosystem execution, numerical
falsifiers, real browser interaction, image checks and source/dependency security.
The optional numerical environment has its own dependency audit. Private benchmark
data and expensive/manual model campaigns remain outside ordinary CI.

## Evidence still required on the chosen host

| Acceptance item | Required observation |
| --- | --- |
| Identity and configuration | Reviewed source/image digest, installed dependency inventory, approved recipes and named operator |
| Access boundary | Working HTTPS, anonymous denial of research APIs, intended operator access and correct credential permissions |
| Resource controls | Measured capacity for the selected workload; enforced CPU, RAM, process and disk limits; no shared writable store across unsupported replicas |
| Monitoring | External availability and certificate monitoring, disk/quota alarms, worker health and an actionable alert destination |
| Durability | Successful real run, service restart, offline backup, restore to a clean location and evidence reverification |
| Rollback | Stop the failed candidate, retain its records, restore the last verified store and start the prior reviewed image |
| Research validity | Existing claim-specific adequacy, privacy, source-rights and qualification evidence |

These are observations from the actual installation. Local tests and CI cannot
attest a host's DNS, TLS, storage guarantees, monitoring ownership or recovery
procedure. Keep deployment readiness blocked until that evidence exists; record
software acceptance and deployment acceptance separately.
