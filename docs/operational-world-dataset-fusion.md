# Operational World Dataset Fusion v1

Veritas Operational World Compiler uses real data to **calibrate distributions and constraints**, not to clone real companies. Generated worlds remain fully synthetic and evaluator-owned.

The fusion target is:

```text
real heterogeneous datasets
        ↓
source-specific validation
        ↓
normalized observations
        ↓
hierarchical calibration profiles
        ↓
OperationalWorldSpec
        ↓
canonical causal company world
        ↓
public system projections + private ground truth
```

## Design rules

1. **Truth is generated, never inferred from noisy source records.** Source data controls realistic priors, topology and artifact form. The compiler still owns canonical ground truth.
2. **No single jurisdiction defines the universal world.** Profiles combine global, regional, country, industry and size-band evidence.
3. **Source provenance survives fusion.** Every empirical distribution lists the source IDs and observation count used to create it.
4. **Bad fields are rejected rather than averaged away.** Publisher quality warnings become ingestion gates.
5. **Units must be normalized before fusion.** Currency, date, quantity and accounting concepts cannot be pooled implicitly.
6. **Bootstrap priors are explicitly labelled.** A profile is `bootstrap_prior`, `hybrid`, or `empirical`; research reports must disclose the state.
7. **Private/sensitive content is not required.** The goal is statistical and structural realism, not reconstruction of a specific real organization.

## Source stack

### 1. GLEIF Golden Copy — global legal-entity structure

Use Level 1 for legal names, entity status, jurisdiction and registered/headquarters address structure. Use Level 2 Relationship Records for direct and ultimate accounting-consolidating parent structure.

Canonical mappings:

| Source concept | Veritas object |
|---|---|
| LEI / legal name | `Organization` identity prior |
| legal jurisdiction | organization jurisdiction distribution |
| legal/headquarters address | location/address-shape prior |
| entity category/status | legal-entity category/lifecycle prior |
| direct parent | `OWNS/CONTROLS` graph prior |
| ultimate parent | group-depth and ultimate-control prior |

Do not treat LEI entities as a representative census of all firms. Use the source primarily for **global corporate topology and identity structure**.

### 2. World Bank Enterprise Surveys — cross-country firm distributions

This is the primary cross-economy source for emerging/developing-market firm characteristics. The survey family covers firm size, sector, labor, finance, infrastructure, innovation, competition, informality and performance.

Normalize into metrics such as:

```text
firm.employee_count
firm.age_years
firm.sales_per_employee
firm.export_share
firm.import_share
labor.permanent_worker_share
finance.external_finance_share
operations.power_outage_frequency
operations.capacity_utilization
```

Questionnaire variable names vary across years/economies; ingestion therefore requires an explicit curated mapping rather than code that guesses columns.

### 3. Open Contracting Data Standard Registry — global procurement topology

OCDS is the core procurement fusion substrate because it provides a common process model spanning planning, tender, award, contract and implementation across many publishers.

Mappings:

| OCDS | Veritas |
|---|---|
| `parties` | buyers, suppliers, procuring entities |
| `planning` | purchase-plan / requirement events |
| `tender` | sourcing/tender events |
| `tender.items` | requested products/services |
| `awards` | award decisions |
| `awards.suppliers` | vendor selection |
| `contracts` | contract objects |
| `implementation.transactions` | payment/implementation observations |
| `milestones` | process-state transitions |
| documents | artifact-type priors |

The first ingestion adapter intentionally extracts **structural** metrics only (party count, tenderer count, awards/process, contracts/process, items/tender). Amount/date metrics require extra normalization and source-specific quality filters.

### 4. Nigeria NOCOPO / BPP — African procurement calibration

NOCOPO is retained as a first-class regional source rather than allowing African procurement worlds to inherit only US/EU priors.

The OCP registry currently reports data from 2021–2026 and substantial planning, award, contract, transaction and milestone coverage. It also records known quality issues, including implausible date values and limitations in release dates.

Policy:

```text
ALLOW: process topology, category counts, party/supplier structure after validation
GATE: dates, durations and time-derived metrics
REJECT: values outside explicit temporal sanity windows
```

Nigeria is one regional calibration source, not a special-case ontology. The same compiler schema is used globally.

### 5. TED Open Data — European procurement

TED contributes high-complexity EU procurement notices and the eProcurement Ontology. Use it for procurement taxonomy, buyer/supplier structures, procedure types, notice complexity and cross-border procurement patterns.

Prefer the Open Data/SPARQL representation or current XML/eForms fields, normalized to the same Veritas procurement metrics used by OCDS.

### 6. USAspending — North American award/transaction structure

Use contract/award and transaction data for US procurement scale, recipient concentration, NAICS/PSC mix, transaction frequency and award lifecycle.

Important fields include award ID, recipient, awarding/funding organization, action date, obligation, NAICS/PSC, place of performance and transaction count.

Do not let US federal procurement dominate private-company procure-to-pay priors; this source calibrates one institutional regime.

### 7. SEC EDGAR XBRL Company Facts — accounting and financial constraints

Use extracted XBRL facts primarily to derive **ratios and accounting relationships**, not to copy public-company absolute scale into SMEs.

Candidate normalized metrics:

```text
finance.revenue_to_assets
finance.ap_to_revenue
finance.ar_to_revenue
finance.inventory_to_revenue
finance.cash_to_assets
finance.gross_margin
finance.operating_margin
finance.current_ratio
finance.debt_to_assets
```

Core invariants such as balance-sheet equality remain deterministic compiler constraints rather than learned probabilities.

### 8. UN Comtrade — global product and trade relationships

Use reporter/partner/product/flow/value data to calibrate cross-border product mix and trading-partner distributions.

Mappings:

```text
reporter → operating/import market
partner → supplier/customer country prior
HS/BEC/SITC product → product family prior
import/export flow → cross-border direction
trade value/share → relative partner/product weighting
```

Comtrade is country-level, so it should shape **mixtures**, not be materialized as firm-level shipment truth.

### 9. Enron email corpus — communication-form calibration only

Use message headers and coarse communication statistics for:

```text
messages per actor/day
recipient-count distribution
reply/thread structure
message-length distribution
working-hour distribution
subject/body formatting
```

Do **not** use email content as canonical operational truth. It is a single-company historical corpus and the current CMU distribution itself warns about authenticity/integrity concerns identified in 2026. It is therefore a renderer/statistical-style source only.

### 10. UCI Online Retail II — transaction and cancellation shape

Recommended additional transactional source for retail/wholesale worlds. It contains more than one million real transactions from a UK non-store retailer, including invoice IDs, product codes, quantities, timestamps, unit prices, customer IDs and customer countries; cancellations are explicitly encoded in invoice identifiers.

Use for:

```text
sales.lines_per_invoice
sales.quantity_per_line
sales.customer_repeat_rate
sales.cancellation_rate
sales.interpurchase_interval
sales.product_concentration
sales.customer_country_mix
```

This source is narrow by industry, so it should only receive meaningful weight in retail/wholesale profiles.

## Fusion hierarchy

A world should not sample directly from a pooled global table. The intended profile hierarchy is:

```text
GLOBAL
  ↓
REGION
  ↓
COUNTRY (when enough observations exist)
  ↓
INDUSTRY
  ↓
SIZE BAND
  ↓
OPERATING MODEL
```

For a metric `m`, use shrinkage toward broader evidence when local samples are sparse:

```text
m_world = λ_local·m_local + λ_region·m_region + λ_global·m_global
```

where the lambdas depend on validated observation count, source reliability and representativeness. A source with many rows does not automatically receive high weight if all rows represent one institution or jurisdiction.

## Cross-source canonical dimensions

Every source is normalized against a shared dimension set:

```text
geography:
  country_code
  region_group

firm:
  industry_family
  size_band
  ownership_form
  age_band

process:
  process_family
  process_stage
  object_type

money:
  source_currency
  normalized_currency
  price_date

classification:
  source_taxonomy
  source_code
  canonical_product_or_industry

provenance:
  source_id
  source_record_id
  extraction_version
  quality_flags
```

## Currency handling

Never pool raw monetary values across currencies.

For empirical calibration, preserve both:

```text
local_amount
source_currency
normalized_usd_or_ppp_amount
normalization_date/method
```

The current compiler accepts `currency_code` and `usd_to_local` in `OperationalWorldSpec.metadata`. This keeps currency conversion explicit while the empirical FX/PPP layer is built.

## Date quality

All date-derived observations pass:

```text
plausible lower/upper year
stage-order constraints
non-negative duration
publisher-specific warnings
maximum duration sanity bounds
```

Known problematic source dates are excluded from duration distributions but the remaining non-temporal fields can still contribute.

## Financial consistency

Observed financial distributions calibrate ratios, but generated worlds must satisfy hard constraints:

```text
assets = liabilities + equity
ledger debits = ledger credits
payment references a valid payable/invoice
invoice references a valid vendor
receipt references a valid PO
PO references a valid request/authority path
inventory cannot silently become negative
```

Scenarios can violate selected operational controls only by creating an explicit private `GroundTruthFinding`.

## Process realism versus document realism

Process realism is upstream:

```text
request → approval → PO → receipt → invoice → payment → ledger
```

Documents are projections:

```text
canonical event
  ├─ ERP record
  ├─ WMS record
  ├─ AP workflow record
  ├─ email
  ├─ PDF/HTML artifact
  └─ ledger/treasury record
```

Language models may render naturalistic text from structured facts, but may not invent canonical facts.

## Building an empirical profile

Prepare a fusion input manifest:

```json
{
  "profile_id": "africa-wholesale-v1",
  "region": "africa",
  "industry": "wholesale_distribution",
  "size_band": "medium",
  "minimum_observations": 50,
  "inputs": [
    {
      "kind": "ocds_jsonl",
      "source_id": "nigeria_nocopo",
      "region": "africa",
      "path": "/data/nocopo.jsonl"
    },
    {
      "kind": "numeric_csv",
      "source_id": "world_bank_enterprise_surveys",
      "region": "africa",
      "industry": "wholesale_distribution",
      "path": "/data/wbes_normalized.csv",
      "metric_columns": {
        "firm.employee_count": "employees",
        "firm.sales_per_employee": "sales_per_employee"
      }
    }
  ]
}
```

Then run:

```bash
python tools/build_operational_calibration.py fusion-input.json \
  --output calibration/africa-wholesale-v1.json
```

If empirical coverage is insufficient for a metric, the output is marked `hybrid` and inherits the explicitly labelled bootstrap prior for that metric.

## Release criteria for a production calibration profile

A profile must not be labelled `empirical` or used for a public benchmark release until:

- source files and extraction versions are recorded;
- every metric has explicit unit semantics;
- geographic and industry coverage is reported;
- outlier and missingness rules are documented;
- known publisher quality warnings are encoded;
- train/public/private worlds use disjoint seeds;
- generated-distribution diagnostics are compared back to source distributions;
- no source-specific real identifiers appear in generated worlds;
- generated worlds pass Veritas structural and leakage validation.

The data fusion layer is therefore a **calibration and constraint system**, not a dataset collage. That distinction is what allows Veritas to be broad without creating internally inconsistent synthetic companies.
