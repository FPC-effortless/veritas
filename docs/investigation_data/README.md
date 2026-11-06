# High-Stakes Investigation Data Program

This subsystem prepares public-source evidence for high-stakes investigation environments without collapsing institutional findings into ground truth or leaking evaluator-only information into agent-visible artifacts.

## Scope

The first acquisition wave targets five environment families:

1. digital/criminal forensics;
2. accident and industrial root-cause investigation;
3. financial/accounting investigation;
4. historical military, intelligence, and diplomatic crisis investigation;
5. cyber incident investigation.

The source catalog lives in `src/investigation_world/investigation_data/source_catalog.json`. It is an allowlist and policy gate, not merely a bibliography.

## Non-negotiable invariants

- Raw third-party corpora are never committed to Git.
- Every acquired artifact has a SHA-256 receipt and a catalog snapshot hash.
- Redirects are accepted only when the resolved host remains on the source allowlist.
- Blocked sources cannot declare downloadable artifacts.
- Review-required sources need an explicit rights-review identifier before acquisition.
- Acquisition permission, redistribution permission, and AI-use permission are separate decisions.
- `official_findings_are_ground_truth` defaults to false and is explicit per source.
- Unknown or missing truth remains `UNKNOWN`; it is never converted to a negative or a pass.
- Public episode serialization and private oracle serialization are separate files.
- Sealed evidence is rejected from public episodes.
- No LLM-generated augmentation becomes authoritative source evidence.

## Why findings and truth are separate

A conviction, regulator settlement, probable-cause finding, intelligence assessment, or historical interpretation can be important evaluator evidence without being equivalent to omniscient ground truth.

The normalized representation therefore separates:

- **public episode state**: what the evaluated agent is allowed to observe at a simulated time;
- **private oracle**: verified truth claims where the source supports them, later evidence, official findings, causal references, and verifier targets;
- **official findings**: conclusions issued by an authority, always provenance-linked and never silently promoted to truth.

Controlled synthetic/reference corpora such as qualifying NIST CFReDS cases and LANL red-team events can support stronger private truth than most real criminal or geopolitical records.

## Source gates

The catalog uses three independent policy dimensions.

### Acquisition

- `approved`: automated acquisition may proceed.
- `review_required`: a reviewer must provide a rights-review identifier.
- `metadata_only`: only artifacts marked as metadata may be acquired.
- `blocked`: acquisition is refused.

### Redistribution

Redistribution is evaluated separately because a source may permit research access while embedded attachments, binaries, photographs, filings, or third-party exhibits have different rights.

### AI use

AI/RL use is independently classified. A source can be downloadable but still excluded from training or evaluation construction.

ACLED is intentionally cataloged as blocked under the currently reviewed EULA. The default open conflict-data lane is UCDP instead.

## Initial source portfolio

| Source | Primary role | Truth use | Default gate |
| --- | --- | --- | --- |
| NIST CFReDS | controlled digital-forensic cases | private truth where case documentation establishes planted artifacts | rights review per selected case |
| Digital Corpora | staged forensic scenarios | private truth for creator-known scenario state | rights review for binary artifacts |
| NTSB aviation census/dockets | accident investigation | evidence reference + official findings | structured census approved; docket attachments separately reviewed |
| SEC EDGAR + AAER | financial investigation | temporal evidence + enforcement findings | acquisition approved; third-party content reviewed |
| UCDP GED 26.1 | conflict world-state/context | context only | CC BY 4.0 with attribution |
| FRUS | retrospective crisis/intelligence evidence | evidence reference | acquisition approved; provenance preserved |
| LANL cyber1 | cyber incident investigation | controlled red-team truth | approved, citation preserved |
| U.S. CSB | industrial root-cause investigation | evidence reference + findings | acquisition approved; embedded media reviewed |
| ACLED | deliberately excluded alternative | none | blocked pending separately reviewed license |

## Reproducible acquisition

Validate the checked-in source catalog:

```bash
veritas-data validate-catalog
```

Inspect policy and seed selection information:

```bash
veritas-data list-sources
veritas-data show-source ucdp-ged-26.1
```

Preview whether an artifact is permitted:

```bash
veritas-data plan ucdp-ged-26.1 ged-26.1-csv
```

Acquire an approved artifact into the ignored local store:

```bash
veritas-data acquire ucdp-ged-26.1 ged-26.1-csv --output .veritas-data
veritas-data acquire ntsb-aviation-census avall-2026-08 --output .veritas-data
```

Each payload gets a sibling `*.provenance.json` receipt containing source/artifact identity, requested and resolved URLs, retrieval timestamp, byte count, SHA-256 digest, catalog digest, and rights-review ID when applicable.

The downloader does **not** unpack archives automatically. This is intentional: extraction is a separate preprocessing stage and must implement archive-path validation, format-specific checks, and dataset-version pinning.

For a review-required source, acquisition remains closed unless the review has been recorded:

```bash
veritas-data acquire <source> <artifact> --rights-review-id RIGHTS-YYYY-NNN
```

A review identifier is an audit reference, not a bypass. It represents a completed source/artifact rights decision outside this code path.

## Raw-to-environment pipeline

```text
source discovery
  -> rights/AI-use review
  -> allowlisted acquisition
  -> immutable raw artifact + SHA-256 receipt
  -> safe extraction / source-specific parsing
  -> normalized source records
  -> entity/time/provenance resolution
  -> evidence graph
  -> fact vs finding vs allegation classification
  -> public/private temporal cut
  -> InvestigationEpisode public file
  -> PrivateInvestigationOracle sealed file
  -> deterministic verifier construction
  -> contamination / duplicate / leakage checks
  -> optional augmentation
```

Augmentation is downstream-only. Generated material must declare its origin and cannot overwrite source provenance or establish new authoritative truth.

## Normalized episode contract

`PublicInvestigationEpisode` contains only agent-visible state:

- episode and source-case identity;
- initial public state;
- public actor descriptors;
- evidence references and provenance;
- observation availability times;
- allowed actions;
- procedural/time/budget constraints.

`PrivateInvestigationOracle` is separately serialized and can contain:

- truth claims with `true`, `false`, or `unknown` status;
- supporting and contradicting evidence IDs;
- later/actual timeline entries where justified;
- official findings as a distinct object class;
- causal reference edges;
- verifier targets.

An episode cannot be exported if its public and private IDs differ, and public serialization rejects sealed evidence.

## Gold-corpus selection

Do not select only famous cases. Famous-case sampling creates memorization and contamination risk and systematically biases toward unusually well-documented failures.

The first gold corpus uses source-specific eligibility filters followed by stratified deterministic selection. When a source offers a stable case identifier, selection within a stratum should be ordered by:

```text
SHA256(source_case_id + catalog_version + selection_id)
```

and take the first `N` qualifying cases. Selection manifests must record every inclusion/exclusion reason.

Initial target lanes are:

- 6 rights-qualified CFReDS reference cases;
- 10 Digital Corpora staged forensic scenarios;
- 20 closed NTSB investigations;
- 20 closed SEC/AAER matters with adequate pre-enforcement filings;
- 10 FRUS crisis episodes, with UCDP context for qualifying post-1989 cases;
- 10 completed CSB investigations;
- 20 LANL red-team-centered cyber windows.

These are development targets, not a claim that the resulting environments are scientifically or frontier qualified.

## Case eligibility rules

A candidate case enters the gold set only when all applicable checks pass:

1. source and artifact rights are compatible with the intended use;
2. source version and case identity are stable enough to pin;
3. there is a defensible temporal cut that prevents outcome leakage;
4. at least two independent evidence paths or modalities are available for nontrivial investigations;
5. the evaluator can distinguish established facts from allegations/findings;
6. there is enough evidence to support at least one falsifiable hypothesis and one plausible alternative;
7. required private references can remain sealed from the evaluated agent;
8. personally identifying or sensitive material has a redaction/release decision;
9. the episode can be deterministically reconstructed from the acquisition receipts and transformation manifest.

Cases with uncertain truth are still useful, but their verifier must reward calibration and evidence support rather than manufacture a binary hidden label.

## PII, victim, and sensitive-record handling

Real investigations can expose names, contact details, medical information, victim information, or operationally sensitive data even when a source is public. The source catalog flags corpora requiring redaction review. Public availability alone is not enough to justify copying all personal data into an RL package.

For gold episodes:

- minimize personal data to what is necessary for the investigative capability;
- pseudonymize identities when identity itself is not causally relevant;
- preserve a private provenance map if reproducibility requires linkage;
- exclude graphic victim imagery and similarly unnecessary high-sensitivity material from the default agent-facing package;
- do not synthesize allegations about real identifiable people beyond what is grounded in the source record.

## Source-specific first-wave preparation

### NIST CFReDS / Digital Corpora

Treat creator-known planted artifacts as the strongest verifier layer. Acquire binary images only after case-level rights review. Preserve original image hashes. Generate environment actions that expose forensic operations rather than dumping the answer key or teacher guide into public state.

### NTSB

Pin the downloadable census snapshot first. Select only closed investigations for the initial gold set. Acquire final reports and docket evidence after case selection, classifying each attachment's rights/privacy status. The NTSB probable-cause statement is an `OfficialFinding`, not automatically a `TruthClaim`.

### SEC

Use an identified User-Agent and SEC-supported access patterns. Build each episode from filings that existed before the simulated cutoff. Later complaint/order/judgment material belongs on the evaluator side unless it was already public at the cutoff. Preserve distinctions among allegation, admitted fact, settlement, and adjudicated finding.

### FRUS / UCDP

Use FRUS primary documents to construct information sets at historical decision timestamps. Later documents are sealed evaluator evidence. UCDP supplies structured event context for compatible post-1989 episodes; it must not become a causal oracle by itself.

### LANL

Acquire the small red-team truth file before the multi-gigabyte telemetry. Construct bounded windows around known red-team events. Matched non-red-team windows are hard negatives only for the statement “not in the known red-team list”; they are not proof that no malicious activity occurred.

### CSB

Build from completed final-report cases first. Separate observed facts, causal analysis, and Board findings. Use CSB videos only as downstream multimodal augmentation after report-grounded episode construction.

## Verification before any training run

Code-level success is not environment qualification. Before using prepared episodes for RL/evaluation, require at minimum:

- schema validation;
- raw artifact checksum verification;
- provenance completeness;
- public/private leakage scan;
- temporal leakage scan;
- duplicate/near-duplicate scan across train/eval splits;
- rights/AI-use gate status;
- redaction-review status where required;
- deterministic reconstruction check;
- verifier falsifier tests;
- ambiguity audit: unknown evidence must remain unknown.

Only after these gates should task-distribution, reward, exploit-resistance, calibration, and frontier-discrimination qualification begin.
