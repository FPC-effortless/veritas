# Frontier Qualification integration notes

No cross-cutting change is required to implement or test Frontier Qualification, and no shared or portability-owned file is modified by this branch.

## Optional post-convergence integration

### Root CLI exposure

- **Desired change:** expose the standalone Frontier commands through the consolidated Veritas CLI after parallel branches converge.
- **Reason:** convenience only; the standalone tools are already complete and composable.
- **Affected API/file:** `src/investigation_world/cli.py` or the later canonical CLI chosen by 0.11.
- **Minimal suggested patch:** add thin command wrappers that call the Frontier package functions without moving any gate logic into the shared CLI.
- **Blocks Frontier Qualification:** no.

### Commercial/release-card surface

- **Desired change:** optionally display a Frontier Qualification report ID/status beside scientific qualification in future commercial/release summaries.
- **Reason:** prevent buyers from conflating scientific validity with demonstrated strong-agent utility.
- **Affected API/file:** future shared commercial/release presentation surface; current candidates include `src/investigation_world/commercial/**` and release documentation.
- **Minimal suggested patch:** add a nullable Frontier report reference/status; never derive it from scientific qualification.
- **Blocks Frontier Qualification:** no.

### Embedding-backed semantic clustering

- **Desired change:** optionally register an embedding-based implementation of the existing semantic-cluster interface.
- **Reason:** higher-fidelity semantic clustering may be useful for large customer corpora.
- **Affected API/file:** no shared file is required for the interface; any future dependency declaration would affect root `pyproject.toml`.
- **Minimal suggested patch:** make the embedding backend an optional extra and inject it through `SemanticClusterBackend`; keep the deterministic offline backend as the default.
- **Blocks Frontier Qualification:** no.
