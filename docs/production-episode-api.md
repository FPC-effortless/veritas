# Bounded episode API deployment

The root Veritas container serves the investigation episode API. This is a
single-process, ephemeral execution surface for a trusted evaluator/orchestrator.
The persistent research workbench uses [TrainLab](../integrations/trainlab/PRODUCTION.md)
and [Research Lab](../integrations/research_lab/README.md); the episode API does
not replace their run stores or recovery records. The Next.js root application
is the public product/inquiry page, not this API or an authenticated research UI.

## Operating boundary

Use one Uvicorn worker and one container instance. Every episode has a live
SQLite search index and a recorder held in that process. Another worker or replica
would have a different store. Session state is intentionally lost at process
restart, expiry, or deletion; a supervisor restart does not resume an evaluation.
Persist the privileged trajectory through the orchestrator before deleting a
completed episode. Retain original authorized inputs and the source identity so
an interrupted episode can be rerun explicitly.

The supported limits are:

| Resource | Limit / response |
| --- | --- |
| Live or finalized episodes retained in one process | 16; new creation receives 503 at capacity |
| Idle episode retention | One hour; cleaned on the next API/health operation, with closed SQLite handles |
| Privileged request body | 8 MiB, checked before JSON parsing |
| Agent request body | 256 KiB, including requests without Content-Length or with an understated value |
| Body arrival deadline | 15 seconds; 408 on timeout |
| Generated task selection | Index 0–255; larger panels can provide their own authorized task/oracle pair |
| Per-episode budget | Cost 1–1,024; tool calls 1–256 |
| Search | Query at most 4,096 characters; result limit 1–100 |
| Container transport | One worker, 64 concurrent connections/tasks, five-second idle keepalive |

These are admission ceilings, not a throughput or latency guarantee. Set host
CPU, memory and PID limits and measure the intended world sizes/concurrency on
that host. The serialized creation boundary prevents concurrent admission from
exceeding the session ceiling. Existing episodes remain usable while creation
is at capacity; export and delete completed work to free a slot. The service
closes all remaining indices on graceful shutdown, and a concurrent delete
returns a controlled 404 to a request holding an already retired session.

## Access and deployment

Provision a high-entropy `VERITAS_ADMIN_TOKEN` through the host's secret manager.
Admin routes require `X-Veritas-Admin-Token`, and reject unauthenticated requests
before reading/parsing their bodies. Do not put a real token in a command line,
URL, source file or public log. Token rotation takes effect on process restart.

An episode ID is an opaque **bearer capability** for that episode's public tool
routes. Anyone who receives it can consume the episode's budget or submit its
answer. Send it only to the assigned agent over an authenticated private channel.
Keep admin routes on the evaluator's private network; put remote agent traffic
behind a TLS/identity-aware proxy or equivalent authenticated private network.
There are no user accounts, tenant roles, per-agent revocation or durable queues
in this API. Deploy the research UI through its own documented authentication.

Publish the container port only on loopback (for example,
`-p 127.0.0.1:8000:8000`) behind the chosen proxy. The image defaults to a non-root
user and one Uvicorn worker, bounded transport concurrency, and disabled access
logs: default URL logs would expose bearer episode IDs and search queries.
Apply the same redaction to proxy and infrastructure logs. Responses use
`Cache-Control: no-store`. Never disable admin authentication to fix proxy access.

Canonical-world integrity checks use explicit conditional exceptions and stay
active under optimized Python. A subprocess regression checks invalid-world
rejection under `python -O`; this does not assert that every unrelated research
operation has been separately qualified for optimized execution.

## Health and operator acceptance

`GET /healthz` is an unauthenticated liveness/aggregate-capacity probe, with the
actual software version and counts; it includes no episode IDs, tasks or tokens.
It can return 200 while orchestration is disabled. `GET /readyz` returns 503 until
an admin token is configured, then 200. Neither probe asserts scientific
qualification, private-source rights, TLS correctness, persistent storage, a
successful external evaluation or available capacity for another episode.

For an installation, record the exact image digest/source, private network/TLS
and anonymous-admin denial, credential distribution, proxy-log redaction,
resource quotas and monitoring. Exercise a representative world through create,
tool calls, submit, privileged trajectory export and deletion. Verify capacity
backpressure, graceful shutdown, and the orchestrator's explicit recovery from
lost ephemeral episodes. Keep all private world/oracle/trajectory material within
its authorized boundary. These host-specific checks are separate from the
constructed source/ASGI tests and CI image liveness check.

The source regression suite is:

```bash
python -m pytest tests/unit/test_episode_server.py tests/unit/test_episode_server_production.py
```

Release publication additionally checks the latest exact-source main/tag CI
`Required` job and mandatory Security jobs, verifies that the canonical tag peels
to the same commit on main, and records `release-gates.json` in the release
checksums/provenance. Missing, skipped, failed, unrelated-ref or older green
evidence cannot substitute for these checks. The checker is read-only; it does
not dispatch jobs, bypass repository protections or grant publication authority.

The release image is built and loaded once, then booted and scanned before any
registry push. Trivy's package-inclusive JSON report is converted into the
CycloneDX SBOM; it is not reconstructed in a separate dependency environment.
Docker inspection, scan metadata and SBOM must all identify the same image ID
and source revision. Publication tags that captured ID without rebuilding, and
the returned registry manifest must reference its exact configuration digest.
The image inspection, scan, health, inventory checks and registry manifest join
the release checksums and provenance. Ordinary CI exercises the same inventory
validator with its non-publishing container build. Missing or mismatched
inventory and high/critical findings block publication.

Production operators should retain and deploy the resulting immutable image
digest. Rebuilding a source commit can resolve newer dependencies; source
identity alone does not reproduce an old runtime image. This workflow validates
the concrete image it publishes and does not claim bit-for-bit rebuilds,
independent supply-chain attestation or zero vulnerabilities of every severity.
