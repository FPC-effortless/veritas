# Installation and compatibility

Keep the existing shared repository and package/import identities. Versions are
independent; the table records current source metadata, not a new publication or
promise that each version is available on PyPI.

| Component | Distribution / import | Source install | Declared Python | Evidence/maturity |
| --- | --- | --- | --- | --- |
| Veritas | `investigation-world` / `investigation_world` | `pip install .` | >=3.12 | 0.11.0 metadata; release authority in BUILD_STATUS |
| Forge | `forge-temporal-data` / `forge_data` | `pip install ./integrations/forge` | >=3.11 | 0.2.0 incubation; temporal/schema integrity, not source-rights attestation |
| TrainLab | `trainlab-local` / `trainlab` | `pip install ./integrations/trainlab` | >=3.11 | 0.3.0 incubation; trusted local execution, not tenant isolation |
| Research Lab OS | `research-lab-os` / `research_lab` | `pip install ./integrations/research_lab` | >=3.11 | 0.1.0 experimental; depends on TrainLab >=0.3,<0.4 |

The full ecosystem requires Python 3.12+. Forge and the base TrainLab runner have
no required runtime dependencies. Forge GUI uses its `workbench` extra; TrainLab
production hosting uses `server`. Research Lab's Forge/Veritas integration needs
those siblings installed explicitly. Runtime/user credentials and datasets are
never part of package installation.

| Integration | Implemented surface | Limit |
| --- | --- | --- |
| Forge → TrainLab | Pinned Dataset reader, as-of examples, declared input/artifact hashes | Bounded local releases; rights are not inferred |
| TrainLab → Research Lab | Existing verified-receipt import and research graph | Integrity does not confer scientific authority |
| Veritas evidence | Shared `EvidenceRecord`, maturity adapter, domain reports | OBSERVED cannot silently become a promotion PASS |
| HUD / Prime | Existing [SRE packaging and adapters](../portability/README.md) | Use exact documented exporter/release gates, not generic feature parity |
| Harbor / OpenEnv / NeMo | Existing [Harbor](../exporters/harbor/README.md), [OpenEnv](../exporters/openenv/README.md) and [NeMo](../exporters/nemo/README.md) exporters | Unsupported semantics and conformance gates remain explicit |
| PyTorch | Optional tensor diagnostics, local CPU DDP, checkpoint/export acceptance | CPU lock: CPython 3.12 Linux x86_64; CUDA unverified here |
| Ray / MLflow / DVC / other GPU providers | Existing external tools can be invoked through trusted argv recipes | No new first-class Ray/MLflow/DVC adapter, remote cancellation or cloud provisioning is claimed |

Root CLI/public-contract versions remain governed by their existing docs. The new
comparison uses `veritas.ecosystem-protocol.v1` and
`veritas.ecosystem-comparison.v1`, wrapping `veritas.shared-evidence.v1`. These
example contracts are deliberately narrow and do not replace verifier, source,
training or release contracts. Breaking changes require an explicit schema/version
change and compatibility review.

The source CI definitions cover Python 3.12 and 3.13 clean installs. A defined
matrix is not evidence that hosted CI ran on a local candidate. Local validation
must report the interpreter it actually used; GPU, target device and production
security gates remain separate. See [the PyTorch limits](../../integrations/trainlab/PYTORCH.md).
