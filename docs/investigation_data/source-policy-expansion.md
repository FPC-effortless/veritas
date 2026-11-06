# DATA-002 source policy expansion

Review date: 2026-08-28

This policy expansion adds two public authorities to the canonical
`investigation_data/source_catalog.json`. It does not download data, create investigation episodes,
or authorize uses outside the artifact classes and rights states recorded in the catalog.

## Policy rule

Public reachability is not a rights decision. Acquisition, redistribution, and AI/training use are
separate policy dimensions. `review_required` and `blocked` remain fail-closed states. A source-level
approval also does not automatically authorize every artifact on the same website.

## CDC National Outbreak Reporting System public dataset

Canonical source ID: `cdc-nors-public`.

Reviewed official evidence:

- CDC NORS data guidance: https://www.cdc.gov/nors/data/index.html
- NORS public dataset identity and license: https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/NORS/5xkq-dg7x
- CDC Use of Agency Materials: https://www.cdc.gov/other/agencymaterials.html

The Data.CDC.gov record identifies dataset `5xkq-dg7x` as **Public Domain U.S. Government** and
provides public API/export access. CDC's agency-materials policy permits reuse of public-domain CDC
material only when reuse also carries a prominent non-endorsement disclaimer, does not
substantively alter the material, and states that the material is available from CDC at no charge.
It also warns that contractor, grantee, third-party, and state/local material can have different
rights. The current policy vocabulary cannot safely encode all of those obligations as attribution
alone.

Policy decision:

- acquisition: `approved` for public dataset `5xkq-dg7x` only;
- redistribution: `review_required` for that public dataset only, because the applicable conditions
  exceed attribution alone;
- AI use: `allowed_with_conditions` for that public dataset only, preserving attribution,
  a prominent non-endorsement disclaimer, no substantive alteration, the CDC no-charge statement,
  and provenance;
- additional NORS requests, underlying state/local records, third-party media, and other CDC
  artifacts are outside this approval and require their own review;
- public NORS data are treated as context/case-selection evidence, not hidden causal truth.

NORS is dynamic. CDC states that reports may be revised after close-out. Every acquisition therefore
needs the dataset asset ID, export timestamp, source metadata, and content hash so a later revision
cannot silently replace the evidence seen by an episode.

The public dataset is disclosure-limited. This policy does not approve more detailed NORS requests
that could include information about specific people or facilities.

## USCG CGMIX Incident Investigation Reports

Canonical source ID: `uscg-cgmix-iir`.

Reviewed official evidence:

- CGMIX Incident Investigation Reports: https://cgmix.uscg.mil/iir/Default.aspx
- CGMIX bulk IIR XLSX export: https://cgmix.uscg.mil/XML/IIRExportSearch.aspx
- CGMIX XML services: https://cgmix.uscg.mil/XML/Default.aspx
- Coast Guard public-information policy: https://www.uscg.mil/Community/faq/
- Coast Guard privacy/security policy: https://www.uscg.mil/disclaim/

CGMIX explicitly provides search and bulk XLSX export for closed reportable marine-casualty
investigations and states that the published database is filtered under federal privacy laws. That is
sufficient to approve acquisition of the public CGMIX export surface.

The Coast Guard's public-information policy also states that Coast Guard Internet information may be
copied or distributed but may not be used for commercial purposes or to imply Coast Guard
endorsement. It does not expressly authorize AI/training use. Veritas therefore does **not** infer
training or commercial redistribution rights from public availability.

Policy decision:

- acquisition: `approved` for the public CGMIX IIR export only;
- redistribution: `review_required`;
- AI use: `review_required`;
- FOIA-only complete reports and linked third-party material are not covered;
- selected records require redaction/privacy review before packaging because incident narratives can
  concern identifiable people, vessels, organizations, injuries, and deaths;
- every export must preserve the exact query, Activity IDs, export date, CGMIX update date, and
  content hash.

CGMIX investigation conclusions are evidence references rather than metaphysical ground truth. The
Coast Guard expressly disclaims guarantees of accuracy, completeness, and timeliness, and the public
IIR database is not necessarily the complete investigative file.

## Explicit non-approvals

This change does not create a blanket approval for CDC.gov, USCG websites, arbitrary government web
pages, YouTube, social media, or linked third-party artifacts. It does not modify the legacy Foundry
source registry and does not make that registry a second source-policy authority.
