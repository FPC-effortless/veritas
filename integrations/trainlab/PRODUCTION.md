# TrainLab production deployment contract

TrainLab 0.2.0 is a production-hardening **candidate** for a single workspace
operated by trusted people and approved recipes. Users can choose a local Python
installation, their own Linux server, or a Linux container host. No cloud vendor
is required. The container includes Forge so the pinned-dataset handoff also
works without a separate runtime installation.

Software readiness, an installed deployment's readiness, and scientific/data
qualification are separate. Do not label an installation production-ready until
its exact-source tests, deployment gates below, and operator acceptance pass.
The repository does not provision DNS, certificates, infrastructure, storage
quotas or monitoring accounts, publish an image, or grant release authority.

## Supported trust and capacity

- Every authenticated operator can view every run and launch every approved
  recipe. Built-in authentication is one shared operator account, with a salted
  PBKDF2-SHA256 password hash (600,000 iterations). Use an identity-aware access
  proxy for individual identity, MFA, access audit or per-user revocation. Keep
  built-in authentication enabled behind that proxy. There are no tenant roles.
- Recipes execute as the service account. They are trusted code, not isolated
  customer jobs. Review commands and dependencies before mounting recipes.
  Hostile recipes, user-uploaded code, tenant isolation and a public training
  service are outside this deployment contract.
- Production job supervision is validated on Linux/POSIX. Process groups are
  killed before outputs are snapshotted; SIGTERM interrupts the active job and
  finalizes its record. Recipes must wait for workers and must not detach them
  into new sessions. Container PID/memory/CPU limits apply to the whole service.
  Windows local use retains its immediate-child termination limitation.
- One job runs at a time per service; run one service per run store. Do not share
  a writable store across replicas or mix independent CLI writers with the
  service. Waitress uses eight request workers, 64 connections, a 15-second idle
  channel timeout, 16 KiB headers and 4 KiB request bodies.
- Each process stream retains at most 16 MiB; excess output fails the job. The
  active store supports 1,000 records and 8 MiB of aggregate run metadata.
  Archive and rotate stores before that limit. This is a bounded workbench, not
  a large distributed queue or an object-storage experiment warehouse.
- Logs are bounded; model artifacts and datasets still require an operator-set
  filesystem quota. A named Docker volume alone does **not** impose a disk quota.
  The Compose template bounds application container logs to 3 × 10 MiB.
- Normal metadata writes use private temporary files, fsync and atomic replace;
  POSIX directory entries are fsynced. Filesystem/hardware durability guarantees
  still depend on the deployment. A power loss can leave unfinished records;
  this is explicit rather than inferred success or automatic resumption.

## Install on a chosen machine

From an exact reviewed checkout:

```bash
python -m venv .venv-trainlab
.venv-trainlab/bin/python -m pip install --require-hashes -r integrations/trainlab/requirements-server.txt
.venv-trainlab/bin/python -m pip install ./integrations/forge './integrations/trainlab[server]'
mkdir -m 700 /path/to/private-trainlab
.venv-trainlab/bin/trainlab init-auth /path/to/private-trainlab/users.json --username operator
.venv-trainlab/bin/trainlab serve --production \
  --auth-file /path/to/private-trainlab/users.json \
  --runs /path/to/private-trainlab/runs \
  --experiments /absolute/path/to/approved-recipes
```

`init-auth` prompts without echoing the password and refuses overwrites. Keep the
file at mode 600 and readable only by the service account. No password belongs in
argv, recipes, logs or source control. Open the printed loopback URL on that same
machine and enter the operator credentials in the browser's HTTP authentication
prompt. Local-only installations do not require a public DNS name or TLS proxy.

For remote users, place a TLS reverse proxy on the same host and add
`--public-origin https://your-trainlab.example`. Keep the backend on loopback.
Only that configured Host/Origin and explicit loopback health requests are
accepted; forwarded identity headers do not bypass authentication. Launches
additionally need the same-origin per-process token. Restarting rotates that
token. Access through arbitrary SSH/browser forwarding hosts requires an
explicit matching configuration; never disable the origin boundary to fix it.

HTTP Basic has no application logout. Close the browser's authenticated session
to remove cached credentials. To revoke access, stop the service, create a new
credential file, atomically replace the old file, and restart. Existing sessions
then fail authentication. Use the upstream identity proxy for user-specific
session policy. A stolen shared password requires rotating that shared account.

## Container deployment on a chosen server

Build from the **repository root**, using an exact reviewed source revision:

```bash
docker build --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -f integrations/trainlab/Dockerfile -t trainlab:reviewed .
```

The image pins its Python base digest and production server wheel hash. The
runtime is Alpine/musl with pure Python packages; pip and ensurepip are removed
after installation. Frameworks requiring glibc, CUDA or compiled extensions need
their own reviewed runtime image and vulnerability scan. Install any additional
approved packages during image build before package-manager removal. The default
image does not claim compatibility with every training framework.
The Dockerfile-specific context allowlist sends only the two packages and examples;
it excludes run stores, credentials, repository private assets and Git metadata.
Build environments with a private CA can supply the optional BuildKit
`proxy_ca` secret; no proxy trust material is embedded into the image.

The Compose template in `deploy/compose.yaml` provides a non-root UID 10001,
read-only root filesystem, dropped capabilities, no privilege escalation,
bounded tmpfs, 128 PIDs, 1 GiB memory, two CPUs, a 15-second stop grace period,
and a persistent run volume. Recipe and credential mounts are read-only. Its
backend port publishes **only on host loopback**.

Configure these operator-owned values before `docker compose up`:

| Variable | Required value |
| --- | --- |
| `TRAINLAB_REVISION` | Exact reviewed commit, used as image tag and OCI revision |
| `TRAINLAB_RECIPES` | Absolute path to a reviewed, dependency-complete recipe directory |
| `TRAINLAB_AUTH_FILE` | Absolute path to the mode-600 credential file, owned by UID 10001 |
| `TRAINLAB_PUBLIC_ORIGIN` | Exact HTTPS origin, for example `https://lab.example.com` |

The host administrator must make the credential file readable by UID 10001 and
keep recipes readable by that account. Do not solve permission errors by making
credentials world-readable or running the service as root. Docker bind mounts do
not translate file ownership automatically. Do not place operator credentials
inside the recipes directory.

Install a TLS reverse proxy on the host, point DNS to it, and permit only HTTPS
ingress. `deploy/Caddyfile` is a minimal Caddy configuration using
`TRAINLAB_DOMAIN`; the backend needs no public port. Add organization-required
identity, request-rate controls and access audit at that boundary. Keep password
headers and experiment payloads out of proxy access logs. TLS certificates and
public ingress must be verified in the actual deployment before approval.

```bash
docker compose -f integrations/trainlab/deploy/compose.yaml config --quiet
docker compose -f integrations/trainlab/deploy/compose.yaml up -d --build
```

Data volume backup, filesystem quota, disk alerts, machine recovery and outbound
network policy remain host responsibilities. Container restrictions reduce host
exposure; trusted recipe code still shares the service account and network.
Never mount a Docker socket, host home directory or general-purpose credentials
into the application container. Recipe commands must use executables available
inside the image, not absolute paths from a developer's virtual environment.
Extend and scan a derived image for frameworks required by real experiments.

## Health, shutdown and restart

`GET /healthz` returns aggregate status without authentication: counts, free
space, unfinished/invalid counts and no names, tokens, commands or data rows.
It reports 503 on malformed records, low free space (less than 64 MiB) or a
store exceeding 1,000 entries. This is metadata/store health, **not** a job
liveness guarantee or continuous artifact-integrity verification. Alert on
unfinished records when the service is idle and inspect them after a host crash.
Use an external monitor for HTTPS availability, disk quota, memory, process
restarts and certificate expiry. Never treat a missing monitor as PASS.

`trainlab health --runs /path/to/runs` uses the same aggregate checks and returns
nonzero for degraded state. Health reads can count an in-progress initial record
write as temporarily invalid; the monitor should require consecutive failures.
The image's healthcheck requires three consecutive failures.

SIGTERM stops HTTP serving and interrupts the active recipe; finalized records
survive restart. Configure a supervisor restart policy and a stop grace period
of at least 15 seconds. SIGKILL or power loss cannot finalize Python records.
After stopping the service **and all job processes**, finalize an unfinished run:

```bash
trainlab recover /path/to/runs/RUN_ID --confirm-no-running-jobs
```

Recovery requires the operator's explicit offline assertion, marks the run
`interrupted`, clears result metrics/artifact claims and retains available log
byte identities. It does not restart training, infer process ownership or
manufacture a successful result. Never run recovery against live workers.

## Backup, restore and rollback

Stop the service and all writers before backup. The archive includes finalized
run records, saved config, recorded logs, metrics and declared artifacts. It
does **not** include original recipe directories, datasets, source code,
credentials, model runtime dependencies or every undeclared output file. Back up
those separately under their privacy/retention policy. Incomplete or corrupt
records fail closed rather than disappearing from the backup.

```bash
trainlab backup /private/backups/runs.zip --runs /path/to/runs
# Retain the printed SHA256 separately from the archive, under access control.
trainlab restore /private/backups/runs.zip --runs /path/to/new-runs --sha256 EXPECTED_SHA256
trainlab health --runs /path/to/new-runs
```

Backups are private mode-600 files and refuse overwrite. The default ceiling is
2 GiB of recorded file bytes and 8,192 files. Restore rejects a wrong archive
pin, duplicate/path-traversal/symlink entries, corrupt files, invalid run schemas
and failed stored integrity checks before creating the new store. It never
overwrites an existing store. Restores are offline and must complete before a
server uses the destination. A hash does not encrypt or authenticate a backup;
use encrypted, access-controlled storage and an independently retained pin.

Test restore on a clean directory before deleting old data. Set retention based
on data rights and recovery objectives; no automatic deletion is performed.
For rollback, stop the service, retain the failed candidate's data, restore the
last known-good backup into a new store, and restart the prior reviewed image
digest against it. Re-entering a source revision alone does not recreate inputs.

## Required acceptance for each release and deployment

Run the package suite, original dashboard browser suite, authenticated production
browser/SIGTERM smoke, container smoke, package build/install, dependency/source
security scans and exact-head independent review. The hosting workflow runs
Python 3.11 and 3.13 and captures container/browser checks on 3.13. Do not expand
the quality baseline or disable checks to pass a release.

```bash
python -m unittest discover -s integrations/trainlab/tests -v
python integrations/trainlab/tests/browser_smoke.py
python integrations/trainlab/tests/production_smoke.py
python integrations/trainlab/tests/container_smoke.py --image trainlab:reviewed
```

On the actual chosen deployment, record: exact image/source identity; successful
HTTPS and anonymous-denial checks; who may access the shared workspace; credential
and recipe permissions; quota/monitoring configuration; a successful run and
comparison; graceful shutdown/restart; backup and clean restore; rollback drill;
and named operational ownership. If any of these are absent, deployment readiness
is **UNKNOWN/BLOCKED**. Authentic-source rights, labels, protected TEST access,
scientific/device evidence and package publication have their own gates.
