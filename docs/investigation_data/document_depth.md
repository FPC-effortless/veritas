# Page-sealed document preparation

Official investigation reports frequently mix observations, source evidence, analysis, findings, recommendations, and outcome-bearing conclusions in one PDF. A document being public does not make every page suitable for an agent-visible investigation episode.

Veritas therefore treats document-depth preparation as a deterministic transform after acquisition and before evidence fusion.

## Boundary

`veritas-data prepare-document` consumes:

1. an already acquired document;
2. its verified provenance receipt;
3. the current source catalog;
4. a reviewed `DocumentPreparationPlan` that classifies every physical PDF page exactly once as `public`, `oracle`, or `ignore`.

The preparation step does not create truth claims, simulation timestamps, official findings, or verifier targets. Those belong to the later evidence-fusion manifest.

The operation fails closed when:

- the acquisition receipt no longer matches the source bytes;
- the plan source/artifact identity differs from the receipt;
- the current catalog blocks AI use or requires an unavailable review identifier;
- the source is not a PDF;
- the PDF is encrypted;
- source size exceeds the configured cap;
- physical page count differs from the reviewed plan;
- page ranges overlap or leave a page unclassified;
- a public page has no extractable text when text scanning is required;
- a public page matches a configured answer-bearing pattern;
- the sealed/oracle root is equal to, inside, or above the public preparation root;
- a deterministic output destination already exists.

Public and oracle PDF slices are physically materialized under separate roots. The public manifest contains only public slices and does not contain source URLs, source case identity, page-range policy, answer patterns, or oracle slice metadata.

## USAF AIB pilot

The first reviewed plan is:

`docs/investigation_data/plans/usaf_aib_kc46_fairbanks_2025-07-16.json`

It targets the official 27-page U.S. Air Force Accident Investigation Board report for the 16 July 2025 KC-46A maintenance mishap at Fairbanks International Airport.

The report demonstrates why section-title splitting is insufficient. Its executive summary states the board's finding, and a later page inside the nominal `SUMMARY OF FACTS` section contains an explicit causal sentence. Both are oracle-side in the checked-in plan, in addition to the formal `STATEMENT OF OPINION` pages.

The non-extractable physical transition page is ignored rather than silently admitted to the public package. This is conservative by design.

Air Force AIB cause and contributing-factor statements remain `evidence_reference` material under the source catalog. They are not promoted to omniscient ground truth.

## Reproducible operator flow

Acquire the pinned catalog artifact into the ignored local acquisition store:

```bash
veritas-data acquire \
  usaf-aib \
  kc46-fairbanks-2025-07-16 \
  --output .veritas-data
```

The acquisition command writes the PDF and a sibling provenance receipt. Pass that receipt to preparation. Public-only preparation is the default:

```bash
veritas-data prepare-document \
  .veritas-data/usaf-aib/kc46-fairbanks-2025-07-16/kc46-fairbanks-2025-07-16-aib.pdf.provenance.json \
  docs/investigation_data/plans/usaf_aib_kc46_fairbanks_2025-07-16.json \
  --acquisition-root .veritas-data \
  --output .veritas-prepared
```

Materialize the answer-bearing slices only when an operator explicitly supplies a physically separate sealed root:

```bash
veritas-data prepare-document \
  .veritas-data/usaf-aib/kc46-fairbanks-2025-07-16/kc46-fairbanks-2025-07-16-aib.pdf.provenance.json \
  docs/investigation_data/plans/usaf_aib_kc46_fairbanks_2025-07-16.json \
  --acquisition-root .veritas-data \
  --output .veritas-prepared \
  --oracle-output .veritas-oracle
```

Prepared slice hashes and source receipt identity are recorded for deterministic downstream fusion.

## Qualification status

This mechanism establishes an implementation and leakage boundary. Historical public AIB cases remain contamination-prone reference/development material. Page sealing does not establish scientific qualification, frontier qualification, or sealed-evaluation cleanliness.

The same preparation primitive can be reused for CISA Cyber Safety Review Board, NIST Disaster and Failure Studies, inspector-general reports, and similar public-authority documents only after a source-specific page review. No automatic heading heuristic is permitted to promote pages to `public`.
