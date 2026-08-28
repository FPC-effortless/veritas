# Veritas Public Investigation Corpus

## Purpose

This program turns public-authority investigation material into reproducible Veritas training/reference corpora while keeping agent-visible evidence separate from verifier-only findings, labels, dispositions, and outcome material.

The program is deliberately not a single dataset. Different source families support different capability-development regimes:

- **breadth corpora** provide tens of thousands of structured episodes for classification, hypothesis formation, evidence weighting, calibration, and curriculum generation;
- **depth corpora** provide document-rich cases for search, evidence synthesis, chronology reconstruction, contradiction handling, source attribution, and long-horizon investigation;
- **sealed evaluation corpora** must be separately qualified and cannot be inferred from the existence of public historical data.

## Current implementation state

| Source family | Domain | Acquisition | Boundary implementation | Intended use |
|---|---|---|---|---|
| CDC NORS | public-health outbreak investigation | automated official CSV acquisition | explicit field-level public/verifier profile | breadth/reference |
| SEC litigation releases | financial misconduct / civil enforcement | automated paginated discovery | complaint/pre-disposition vs later disposition document pairing | breadth + document/reference |
| NTSB | transport accident investigation | foundation registry + seeded document cases | document-level public/verifier separation | depth/reference |
| CSB | industrial/chemical accident investigation | foundation registry + seeded document cases | document-level public/verifier separation | depth/reference |
| USCG CGMIX | marine casualty | registered; structured service/export available | adapter pending | breadth/reference |
| NASA ASRS | aviation human factors | registered | adapter pending | breadth/reference; weak oracle |
| TSB Canada / ATSB / AAIB / RAIB / MAIB | transport safety | registered | adapter pending | jurisdictional OOD/reference |
| NIOSH FFFIPP | fireground / occupational safety | registered | adapter pending | depth/reference |
| FBI Vault | criminal / counterintelligence / historical investigations | registered | no intrinsic verifier | document-navigation/reference |
| CISA CSRB | cyber incidents | registered | report section separation pending | depth/reference |
| NIST Disaster and Failure Studies | structural / disaster / fire failure | registered | report section separation pending | depth/reference |
| USAF AIB | military aviation / operational safety | registered | report section separation pending | depth/reference |
| DoD OIG | military oversight / administrative investigation | registered | report section separation pending | depth/reference |
| FEMA EMI | incident command doctrine | registered | procedural augmentation | policy/process augmentation |

## Corpus architecture

### 1. Raw acquisition zone

Raw source exports may contain both evidence and answer-bearing fields. They are therefore **operator-side staging material**, not public corpus artifacts.

For structured sources the compiler requires every input column to be classified as exactly one of:

- `public` — permissible agent-visible evidence;
- `verifier` — answer/outcome material kept outside the agent projection;
- `ignore` — deliberately unused material.

Any unclassified input column aborts compilation. This makes upstream schema drift a build failure rather than a silent label leak.

### 2. Public corpus

Agent-facing structured records contain:

- opaque case identity;
- source family identity;
- domain;
- event date/location where explicitly public evidence;
- task objective;
- approved evidence fields.

They do **not** contain:

- verifier fields or values;
- verifier artifact identifiers/URLs;
- raw source row number;
- raw structured-source URL when that URL exposes labels;
- verifier hash;
- operator notes.

For document cases, final reports/findings/judgments are excluded from the public projection unless a source-specific policy explicitly classifies a document as evidence.

### 3. Verifier corpus

The verifier projection may contain source provenance, raw row position, findings/outcomes, and verifier references. It must remain separated from the evaluated agent surface.

Verifier semantics are source-dependent. A verifier is not automatically metaphysical ground truth:

| Source | Verifier semantics |
|---|---|
| NTSB / CSB / transport safety boards | formal investigation findings / probable or causal conclusions |
| CDC NORS | public-health surveillance/investigation finding |
| SEC litigation | legal or procedural disposition; complaints remain allegations |
| NIST | technical failure finding, not legal fault or negligence |
| FBI Vault | no intrinsic oracle; independent linkage required |
| NASA ASRS | self-report plus expert coding; not a formal accident finding |
| DoD OIG | administrative/audit/investigative finding subject to report scope and redaction |

## Implemented breadth corpus: CDC NORS

The official CDC metadata currently describes 66,713 NORS rows. The current field profile exposes outbreak context such as year/month/state, primary transmission mode, setting, illness/hospitalization/death counts, water exposure/type, and animal type.

The verifier side withholds:

- etiology;
- serotype/genotype;
- etiology status;
- food vehicle;
- contaminated ingredient;
- IFSAC category.

This supports tasks such as etiologic inference and implicated-source inference without putting those labels in the agent record.

NORS remains **public historical reference data**. It is useful for training, calibration, curriculum construction, and pipeline evaluation. It is not evidence of contamination-resistant benchmark quality.

## Implemented legal/financial corpus: SEC litigation

The SEC litigation-release index currently contains thousands of civil-action releases. The discovery adapter looks for rows that contain both:

1. a pre-disposition filing such as a complaint, application, memorandum, declaration, subpoena filing, or other approved evidence document; and
2. a later outcome-bearing document such as a judgment, dismissal, settlement, consent, stipulation, decree, or court opinion.

Only the first group is agent-visible. Later outcome documents remain verifier references. The release narrative page itself is not emitted to the agent because it may summarize the outcome.

The task is a legal-process inference task. A court disposition is not represented as proof that every allegation in an SEC complaint was factually true.

## Qualification states

Public historical corpora should use the following maturity states.

### `reference_only`

Appropriate for historical public cases whose outcomes are already public and may be present in model pretraining. Current NORS, SEC, NTSB seed, and CSB seed material belong here.

### `holdout_candidate`

A candidate set may be created using temporal, jurisdictional, source-family, or procedural separation. Candidate status does not establish cleanliness. Before promotion it requires at minimum:

- source/train overlap audit;
- exact and near-duplicate audit;
- label/artifact leakage audit;
- temporal/publication audit;
- contamination-risk assessment for evaluated models;
- distribution and stratum coverage checks;
- deterministic reconstruction/replay where promised.

### `scientifically_qualified`

This status requires the active Veritas scientific qualification contract. It is never granted automatically by corpus acquisition or successful CI.

### `sealed_evaluation`

The strongest evaluation product should be built from material whose verifier outcome was not available to the evaluated model during the relevant cutoff, or from newly commissioned/synthetic-but-validated cases with independent expert adjudication. Public historical cases alone cannot establish this state.

## Target product shape

The corpus program should converge on three complementary assets rather than one monolithic benchmark:

1. **Reference breadth:** at least 100,000 structured/public-authority episodes across public health, transport, marine safety, aviation human factors, and financial/legal processes.
2. **Investigation depth:** thousands of document-rich cases across transport, industrial, cyber, structural/disaster, fireground, military accident, oversight, and historical investigative records.
3. **Qualified sealed panel:** hundreds to low thousands of high-value cases with independently controlled verifier material, contamination audit, adversarial variants, expert disagreement records, and task-level qualification evidence.

These are program targets, not current achievement claims.

## Operational commands

Install the package and use the dedicated corpus CLI:

```bash
veritas-corpus acquire-cdc-nors --output-root investigation_corpus/cdc_nors
```

```bash
veritas-corpus discover-sec-litigation \
  --maximum-cases 2000 \
  --public-output investigation_corpus/sec_litigation/public.json
```

For an already acquired structured source:

```bash
veritas-corpus compile-structured \
  datasets/public_investigations/profiles/cdc_nors_v1.json \
  /private/staging/nors.csv \
  cdc-nors-example \
  1.0.0 \
  --output-root investigation_corpus/nors-example
```

A manually dispatched GitHub Actions workflow can build CDC NORS or SEC corpora. Verifier artifact upload is opt-in and separate from the public artifact.

## Next source adapters

Priority order after NORS and SEC:

1. **USCG CGMIX** — structured marine-casualty service/export; high leverage for transport breadth.
2. **NASA ASRS** — high-volume incident narratives and coding; useful for human-factors and diagnostic tasks, with weaker oracle semantics.
3. **NTSB CAROL/dockets** — document-rich causal investigation; bulk/API access has transition/authentication constraints, so adapters must not assume an unavailable subscription key.
4. **CISA CSRB / NIST / USAF AIB** — report-section extraction for cyber, disaster/failure, and military-accident depth.
5. **FBI Vault / DoD OIG** — document-rich investigative reasoning where verifier truth must be supplied or linked independently rather than inferred from the source archive itself.
