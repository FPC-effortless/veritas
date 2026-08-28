# Public operational records for External Investigation

Veritas can construct high-stakes investigation environments from public organizations that publish both factual evidence and independently resolved outcomes. The dataset contract in `foundry.public_investigation_data` preserves that natural separation instead of flattening cases into question-answer pairs.

## Dataset contract

A `PublicInvestigationCase` contains:

- stable case/source identity;
- event date, jurisdiction, domain, and status;
- an agent-facing investigation objective;
- `public_evidence` with typed provenance links;
- `verifier_references` containing final findings or other privileged scoring references;
- non-truth-bearing metadata.

Supported evidence roles include initial and factual reports, interviews, transcripts, telemetry, photos, video, audio, procedures, regulations, party submissions, and other evidence.

The first source registry covers NTSB, CSB, USCG CGMIX, TSB Canada, ATSB, UK AAIB/RAIB/MAIB, NASA ASRS, NIOSH FFFIPP, and FEMA EMI. These sources span transportation, chemical/process safety, firefighting, emergency management, and aviation incident reporting.

## Seed v1

The initial reference set contains four completed cases:

| Source | Case | Domain |
| --- | --- | --- |
| NTSB | DCA24MM031 — Dali / Francis Scott Key Bridge | marine transportation |
| NTSB | RRD23MR005 — East Palestine derailment | rail / hazardous materials |
| CSB | 2005-04-I-TX — BP Texas City | chemical process safety |
| CSB | 2013-02-I-TX — West Fertilizer | chemical distribution / emergency response |

These are intentionally **reference/training cases**, not sealed benchmark cases. The manifests link representative factual evidence and multimedia separately from official final findings.

## Acquisition architecture

Large-scale acquisition should be adapter-based rather than one generalized scraper:

1. **NTSB** — ingest CAROL case identity and structured metadata; enumerate docket artifacts; classify factual evidence; keep completed-investigation findings private.
2. **CSB** — ingest investigation indexes and report/video links; separate preliminary/factual products from final causal findings.
3. **USCG CGMIX** — ingest closed-investigation search exports and case records; normalize marine casualty identities and exhibits.
4. **TSB/ATSB/AAIB/RAIB/MAIB** — normalize international investigation reports into the common case schema while retaining source-native taxonomies.
5. **NASA ASRS** — ingest high-volume deidentified narratives as shorter operational episodes, with analyst coding retained according to the intended task/verifier boundary.
6. **NIOSH FFFIPP/FEMA EMI** — use fatality investigations and incident-command doctrine to construct fireground and emergency-command worlds.

Adapters should emit immutable acquisition manifests. Content extraction, chunking, multimodal processing, and world compilation are downstream stages with their own versions and hashes.

## Holdout policy

Public data does not automatically make a valid public benchmark. If final reports are broadly indexed on the web, a frontier model may already know the outcome. Veritas therefore needs at least two evaluation modes:

- **historical capability evaluation** — tests evidence-grounded reasoning on known historical incidents; useful but contamination-prone;
- **sealed prospective/late-discovered evaluation** — cases frozen after split policy is established, with leakage audits and verifier material withheld from model-visible surfaces.

The seed dataset supports development of the pipeline and task mechanics. It does not establish scientific qualification or contamination resistance.
