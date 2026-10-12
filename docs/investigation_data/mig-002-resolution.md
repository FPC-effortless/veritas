# MIG-002 parity resolution

MIG-002 closes the legacy public-investigation Foundry migration by recording which capabilities were migrated, rejected, or superseded after canonical investigation-data parity landed. This note is a provenance and architecture record only. It does not authorize scientific, Frontier, training, commercial, release, or sealed-data claims.

## Canonical authority

Current `main` uses `investigation_world.investigation_data` as the single active authority for investigation source policy, artifact-scoped acquisition, and structured-corpus compilation. The legacy Foundry registry/materializer stack from PR #118 never entered `main`; PR #118 is closed unmerged as superseded, while PR #125 remains closed historical provenance. No production deletion is required or authorized by MIG-002.

The canonical replacement sequence is:

- DATA-002 / #186 / PR #258 for reviewed CDC NORS and USCG CGMIX source-policy surfaces;
- MIG-001 / #184 / PR #134 for the canonical CSV/JSON/JSONL/XLSX structured-corpus compiler and public/verifier projection boundary;
- the existing `investigation_data` acquisition/preparation layer for HTTPS acquisition, redirect restrictions, byte limits, hashing, receipts, and policy enforcement.

A current-main code search found no references to the legacy `public_investigations` registry/materializer names or to the legacy adapter entry points `fetch_cdc_nors_csv`, `parse_uscg_soap_response`, or `assemble_uscg_iir_record`. This is evidence that current consumers do not depend on those branch-only semantics; it is not a claim that future products cannot need separately contracted adapters.

## Capability dispositions

| Legacy capability | Disposition | Resolution |
| --- | --- | --- |
| Broad `datasets/public_investigations/source_registry.json` policy authority | `REJECTED_WITH_REASON` | A duplicate source-policy authority would split canonical rights semantics. `investigation_data/source_catalog.json` plus the strict investigation-data models remain authoritative. |
| Public/verifier case separation and sanitized projections | `MIGRATED` | Canonical investigation-data episode/fusion and structured-corpus projection semantics provide the public/private boundary without importing the legacy registry. |
| Generic HTTPS acquisition, redirect allowlisting, byte-size limits, hashing, and provenance receipt | `MIGRATED` | Canonical `investigation_data` acquisition/preparation owns these semantics. The legacy downloader/materializer is not retained as a second acquisition path. |
| Structured CSV/JSON/JSONL/XLSX field-exposure compiler | `MIGRATED` | MIG-001 / #184 / PR #134 provides the canonical structured-corpus compiler, including deterministic public/verifier projections and fail-closed rights evidence. |
| CDC NORS automated fetch/profile adapter | `REJECTED_WITH_REASON` | Gold-10 is CSB-specific. DATA-002 deliberately models NORS as a manual, artifact-scoped reviewed surface. No current-main consumer requires the legacy automated fetcher. A future NORS product needs its own canonical adapter Work Contract. |
| USCG CGMIX SOAP discovery/parser/staging | `REJECTED_WITH_REASON` | DATA-002 approves a reviewed public CGMIX export surface, not blanket legacy SOAP acquisition. Privacy/redaction, redistribution, and AI-use review remain explicit boundaries. No current-main consumer requires the legacy SOAP adapter. |
| SEC civil-litigation discovery and pre-disposition/outcome pairing | `REJECTED_WITH_REASON` | It is outside the CSB Gold-10 flagship and is not equivalent to the existing canonical SEC source policy. Any future pairing adapter requires a source-specific contract, rights review, and tests. |
| Legacy corpus CLI and GitHub workflow | `REJECTED_WITH_REASON` | They are coupled to the duplicate registry/materializer. Required commands should be rebuilt only on canonical primitives when an active product lane demonstrates demand. |
| Broad unreviewed source-registry expansion | `REJECTED_WITH_REASON` | Public reachability is not artifact-scoped acquisition, redistribution, or AI-use approval. Each future authority requires independent canonical source-policy review. |
| BP Texas City seed | `SUPERSEDED` | Canonical CSB Gold-10 case `2005-04-I-TX` provides the maintained case path with verified report provenance. |
| West Fertilizer seed | `SUPERSEDED` | Canonical CSB Gold-10 case `2013-02-I-TX` provides the maintained case path with verified report provenance. |
| NTSB Dali seed `DCA24MM031` | `REJECTED_WITH_REASON` | It is outside the CSB Gold-10 selection and lacks an exact Gold artifact/review/truth contract in this lane. It may return only through a separate NTSB case-selection contract. |
| NTSB East Palestine seed `RRD23MR005` | `REJECTED_WITH_REASON` | It is outside the CSB Gold-10 selection and lacks an exact Gold artifact/review/truth contract in this lane. It may return only through a separate NTSB case-selection contract. |

## Preservation and non-goals

MIG-002 preserves the legacy PR history instead of merging or deleting it. The historical implementations remain available in PR #118/#125 for future research, but they are not active canonical authorities.

This resolution intentionally makes no production-code changes. It does not reinterpret source rights, grant redistribution or AI-use approval, qualify an environment scientifically, establish Frontier value, authorize training use, or declare commercial/release readiness.

## Closure invariant

MIG-002 is complete only while all of the following remain true:

1. canonical investigation-data policy/acquisition/structured-corpus semantics have one active authority on `main`;
2. no live consumer depends on the legacy Foundry registry/materializer or rejected adapters;
3. rejected capabilities can return only through new, independently scoped Work Contracts rather than by reviving the duplicate authority wholesale;
4. the legacy PRs remain preserved as historical provenance rather than being rewritten into canonical history.
