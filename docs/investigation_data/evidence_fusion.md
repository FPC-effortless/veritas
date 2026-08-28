# Investigation Evidence Fusion

Veritas treats multimodal fusion as an evidence-construction problem, not as unconstrained document concatenation.

The objective is to combine structured records, documents, video, audio, images, sensor data, transcripts, forensic artifacts, and carefully marked derived material into one investigation episode while preserving:

- exact provenance;
- case identity;
- information-release time;
- public/private boundaries;
- evidentiary role;
- derivation lineage;
- deterministic compilation.

## Core rule

A model may only observe evidence that was actually available at the simulated investigation time.

Later hearings, final reports, post-event documentaries, later-released video, retrospective analysis, and future database rows must be withheld until their `available_from` time. Missing temporal provenance is not interpreted as available.

Only static `context` evidence may use `timeless=true`.

## EvidenceFragment

Every fusion input is represented as an `EvidenceFragment` with:

- `fragment_id`;
- source and source-artifact identity;
- one or more case IDs;
- modality;
- epistemic role;
- derivation kind;
- sensitivity;
- locator and content reference;
- optional SHA-256;
- observation and availability timestamps;
- optional media segment boundaries;
- reliability;
- parent-fragment lineage;
- claim support/contradiction annotations.

Supported modalities are:

`structured`, `document`, `video`, `audio`, `image`, `sensor`, `transcript`, `forensic`, and `derived`.

Epistemic roles are independent of modality. A video can be testimony, primary evidence, context, an official finding, or derived material. Modality must never be used as a proxy for truth.

## Video and YouTube

Official video hosted on YouTube or another platform is represented as externally located evidence. The fusion layer does not assume that platform availability grants redistribution or AI-training rights.

Recommended pattern:

1. retain the official publisher as the source identity;
2. retain the external video URL as `locator`;
3. store an operator-authorized local caption/transcript/frame derivative as `content_ref` when permitted;
4. assign `available_from` to the earliest defensible public release time;
5. identify a precise segment with `segment_start_seconds` and `segment_end_seconds` when only part of a video is evidence;
6. make extracted captions/transcripts children of the original video fragment;
7. preserve artifact hashes for locally materialized derivatives.

Do not silently bulk-download YouTube content or treat an automatically generated transcript as authoritative evidence. Platform terms and source-specific rights remain governed by the acquisition catalog and any required rights review.

## Lineage safety

Extracted and transformed evidence must name parent fragments.

Veritas rejects:

- missing parents;
- evidence-lineage cycles;
- a derived artifact becoming available before its parent;
- public/restricted evidence derived from sealed ancestry.

This prevents private evaluator truth from being accidentally converted into an agent-visible summary or synthetic artifact.

## Case linking

A fragment must share at least one `case_id` with the episode's `source_case_ids`.

Cross-source fusion is therefore explicit. For example, an aviation episode may link a structured NTSB database row, a docket document, a hearing-video segment, a transcript extracted from that segment, and a later final finding. All of those items must still identify the same case.

`EvidenceRelation` adds explicit graph edges such as:

- `supports`;
- `contradicts`;
- `corroborates`;
- `derived_from`;
- `same_event`;
- `same_actor`.

Relations do not override provenance or truth semantics.

## Truth separation

`FusionManifest` continues the acquisition subsystem's strict split between:

- agent-visible evidence;
- private ground-truth claims;
- institutional/official findings.

An official finding is not automatically promoted to ground truth.

Sealed `PRIVATE_TRUTH` fragments never enter the public episode. The private oracle is compiled separately through the existing `InvestigationEpisodeBundle` boundary.

## Temporal compilation

For a manifest with simulated cutoff `T`:

- non-sealed evidence with `available_from <= T` becomes public episode evidence;
- non-sealed evidence with `available_from > T` is reported as `withheld_future_fragment_ids`;
- sealed evidence is reported separately and never serialized into the public artifact;
- timeless context is public independent of `T` only when explicitly classified as `context`.

The resulting `FusionReport` records the manifest hash, included/withheld/sealed fragment IDs, modality counts, source identities, and relation count.

## CLI

Validate a manifest:

```bash
veritas-data validate-fusion path/to/manifest.json
```

Compile it:

```bash
veritas-data fuse path/to/manifest.json --output .veritas-fused
```

The compiler writes separate:

- `public.json`;
- `oracle.json`;
- `fusion_report.json`.

The existing public serialization leakage guard remains authoritative for the public/oracle split.

## Example video lineage

```json
{
  "fragment_id": "hearing-video",
  "source_id": "official-investigator-media",
  "source_artifact_id": "hearing-2026-01",
  "case_ids": ["CASE-123"],
  "modality": "video",
  "epistemic_role": "testimony",
  "derivation": "original",
  "sensitivity": "public",
  "locator": "https://video-platform.example/watch?v=official",
  "content_ref": "external-media://hearing-2026-01",
  "available_from": "2026-01-10T15:00:00Z",
  "segment_start_seconds": 540.0,
  "segment_end_seconds": 615.0,
  "reliability": "medium"
}
```

An extracted transcript would use `derivation="extracted"`, `epistemic_role="derived"`, and `parent_fragment_ids=["hearing-video"]`. It cannot be temporally available before the parent video.

## Scientific status

This subsystem establishes implementation-level provenance, temporal, lineage, and sealing guarantees. It does not by itself scientifically qualify an investigation environment or establish frontier training value. Those require separate qualification evidence under the repository's scientific contracts.
