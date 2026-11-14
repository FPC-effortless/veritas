# Offline diagnostic browser and portable bundles

`trainlab.diagnostic_bundle` collects pinned public-authorized diagnostic reports
into a responsive offline HTML browser, raw JSON and a verifiable ZIP. It extends
roadmap features 2, 21, 22 and 24. It imports evidence without executing code,
loading community plugins, or promoting scientific qualification.

## Create and inspect

```bash
python -m trainlab.diagnostic_bundle create --spec spec.json --sha256 SPEC_SHA --root new-bundle
python -m trainlab.diagnostic_bundle verify --root new-bundle --sha256 MANIFEST_SHA
python -m trainlab.diagnostic_bundle export --root new-bundle --sha256 MANIFEST_SHA --zip report.zip
```

Retain the printed manifest SHA separately. Open `new-bundle/index.html` in a
browser; no server, network, fonts or external scripts are needed. Filter by
TESTED, FAILED, INCONCLUSIVE, UNSUPPORTED or NOT_RUN. Expand a finding to inspect
its source excerpt, raw JSON, hash and review notes. Small screens use one column.
Raw report JSON is retained unchanged; excerpts are visibly truncated at 8,000
characters. This is a report browser, not a model debugger or universal error UI.

The example accepts only explicitly pinned public constructed report files:

```bash
python integrations/trainlab/examples/build_diagnostic_bundle.py \
  --root /tmp/new-diagnostic-browser \
  --report /path/to/public/pack-reports.json REPORT_SHA
```

Repeat `--report PATH SHA256` for dataset, state, training/comparison and
quality–cost reports. Existing Forge/TrainLab/Research Lab runs remain the source
of evidence; packaging does not rerun or requalify them. The example extracts
supported status nodes from dictionaries and lists, and
adds explicit GPU/native-model/productivity coverage gaps. It performs no fits.

## Specification contract

A finite JSON object has exactly:

- `schema`: `trainlab.diagnostic-bundle-spec.v1`.
- `title`: nonempty text.
- `data_classification`: `PUBLIC_AUTHORIZED` or `CONSTRUCTED_PUBLIC`.
- `packs`: 1–64 metadata objects with unique `id`, `version`, `applicability`,
  `dependencies` (text list), `cost` (declared text), `evidence_requirements` (text
  list) and `limitations` (text list).
- `findings`: 1–200 objects with unique `id`, known `pack_id`, `kind`, `summary`,
  `status`, `evidence` and `reviews`.

`kind` is observation, hypothesis, intervention or conclusion. It classifies the
author's statement, not its correctness. A hypothesis displayed next to a TESTED
check is still a hypothesis. Pack cost/applicability and reviewer identity are
caller declarations, not authenticated or independently measured claims.

For inspected findings, `evidence` contains `path`, `sha256` and `pointer` (a list
of dictionary keys or nonnegative integer list indices into the source report). The selected node's `status` must
exactly equal the finding status. Importing FAILED evidence as TESTED is rejected.
For UNSUPPORTED/NOT_RUN coverage entries, `evidence` may be null. Other statuses
require pinned evidence. `reviews` is a list of up to eight objects containing
`reviewer`, `note` and `report_sha256`; each hash must match that finding's source.
Reviews of absent evidence and stale hashes are rejected. Review authorship is
not authenticated and does not satisfy the repository's merge review gate.

Source paths must be safe relative paths within the specification directory;
absolute paths, traversal, symlinks and non-files are rejected. Hashes are checked
before JSON interpretation. Finite JSON is bounded to 16 MiB per file and nesting
32, with duplicate keys/nonfinite values rejected. At most 32 source files and
32 MiB aggregate source bytes are accepted. Existing destinations are never
overwritten. Public authorization is an operator declaration, not a private-data
sanitizer: never point this tool at protected TEST rows or private source files.

## Integrity and portability

The manifest binds exact bytes, sizes and paths for `index.html`, `bundle.json`
and raw evidence. Verification requires an externally retained manifest hash and
rejects changed/missing/unexpected files, duplicate entries and symlinks. It
establishes byte integrity, not truth, authenticity, signatures or independent
execution. A malicious author can create a self-consistent false report.

ZIP export uses the already verified in-memory byte snapshot, avoiding a second
unverified read of files after verification. It never extracts imported ZIPs or
executes imported reproduction commands. A partially interrupted creation remains
unqualified until all expected files and the manifest verify. Filesystem races
against hostile concurrent writers and signed community-code distribution are
outside the trusted local workflow. Preserve the original run receipts and source
commit; the browser is an additional evidence view, not their replacement.

All imported text is HTML-escaped. The offline page permits only its fixed
hash-authorized filtering script; imported strings cannot become scripts, links,
styles or remote assets. Review notes bind report bytes, not a mutable web URL.

## Remaining work

Native tracker/profiler importers, authenticated live collaboration, signed pack
loading, generalized executable reproductions, hypothesis ranking/dispatch and
real-project repair/productivity acceptance remain outstanding. Neither a portable
report nor a green unit suite establishes diagnostic sensitivity on arbitrary
projects or that all 24 roadmap features are complete.

## Browser acceptance

The TrainLab local workbench workflow builds a public constructed bundle and
opens its offline page in Chromium. The check visits every status filter,
inspects a finding with the keyboard, opens its raw JSON, checks a 320px
viewport and rejects external network requests or script errors. Desktop and
mobile captures are retained with the workflow evidence.

To repeat in an environment where Playwright Chromium can launch:

```bash
PYTHONPATH=integrations/trainlab/src python \
  integrations/trainlab/tests/diagnostic_bundle_browser_smoke.py \
  --evidence /tmp/veritas-diagnostic-browser
```

The larger executed bundle contains 89 status nodes from ten public reports.
Use its manifest pin for byte verification. Browser acceptance and bundle
integrity are recorded separately.
