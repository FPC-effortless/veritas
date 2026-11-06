from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    QuantileDistribution,
    RegionGroup,
    WeightedCategory,
)


class DatasetSourceSpec(BaseModel):
    """One source in the operational-world calibration corpus.

    Source data is never copied directly into generated worlds. It is normalized into
    distributions, categorical frequencies and structural constraints with provenance.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    provider: str
    access_url: str
    domains: list[str]
    geography: list[str]
    granularity: str
    roles: list[str]
    quality: str
    caveats: list[str] = Field(default_factory=list)


DEFAULT_SOURCES: tuple[DatasetSourceSpec, ...] = (
    DatasetSourceSpec(
        source_id="gleif_lei",
        title="GLEIF Golden Copy Level 1 and Level 2",
        provider="Global Legal Entity Identifier Foundation",
        access_url="https://www.gleif.org/en/lei-data/gleif-golden-copy",
        domains=["legal_entities", "addresses", "ownership"],
        geography=["global"],
        granularity="legal_entity_and_parent_relationship",
        roles=["entity_shape", "jurisdiction_mix", "ownership_graph", "address_shape"],
        quality="high",
        caveats=[
            "LEI coverage is not a representative census of all firms.",
            "Parent relationships reflect accounting-consolidation relationships when reported.",
        ],
    ),
    DatasetSourceSpec(
        source_id="world_bank_enterprise_surveys",
        title="World Bank Enterprise Surveys",
        provider="World Bank Group",
        access_url="https://microdata.worldbank.org/collections/enterprise_surveys",
        domains=["firmographics", "labor", "finance", "operations", "business_environment"],
        geography=["emerging_markets", "developing_economies", "cross_country"],
        granularity="firm",
        roles=["firm_size", "industry_mix", "labor_shape", "operating_context"],
        quality="high",
        caveats=[
            "Sampling frames and questionnaire versions vary by economy and year.",
            "Formal-sector surveys generally target firms with five or more employees.",
        ],
    ),
    DatasetSourceSpec(
        source_id="ocds_registry",
        title="Open Contracting Data Registry",
        provider="Open Contracting Partnership",
        access_url="https://data.open-contracting.org/",
        domains=["procurement", "tender", "award", "contract", "implementation"],
        geography=["global", "100_plus_publishers"],
        granularity="contracting_process",
        roles=["procurement_topology", "supplier_mix", "process_depth", "document_shape"],
        quality="mixed",
        caveats=[
            "Publisher completeness and data quality vary materially.",
            "Use publisher-specific quality metadata before admitting observations.",
        ],
    ),
    DatasetSourceSpec(
        source_id="nigeria_nocopo",
        title="Nigeria Open Contracting Portal / BPP",
        provider="Nigeria Bureau of Public Procurement via OCP Registry",
        access_url="https://data.open-contracting.org/en/publication/64",
        domains=["procurement", "planning", "award", "contract", "milestones"],
        geography=["nigeria", "africa"],
        granularity="contracting_process",
        roles=["african_procurement_shape", "milestone_density", "supplier_process_shape"],
        quality="mixed",
        caveats=[
            "Registry notes invalid/extreme dates and release-date limitations.",
            "Date-derived metrics require explicit sanity filtering.",
        ],
    ),
    DatasetSourceSpec(
        source_id="italy_anac_ocds",
        title="Italy ANAC via OCP Data Registry",
        provider="Autorita Nazionale Anticorruzione via Open Contracting Partnership",
        access_url="https://data.open-contracting.org/en/publication/117",
        domains=["procurement", "award", "contract"],
        geography=["italy", "europe"],
        granularity="contracting_process",
        roles=["european_procurement_shape", "process_depth", "supplier_process_shape"],
        quality="mixed",
        caveats=["Publisher-specific date and completeness issues require field-level gates."],
    ),
    DatasetSourceSpec(
        source_id="uruguay_arce_ocds",
        title="Uruguay ARCE via OCP Data Registry",
        provider="Agencia Reguladora de Compras Estatales via Open Contracting Partnership",
        access_url="https://data.open-contracting.org/en/publication/43",
        domains=["procurement", "award", "contract", "implementation"],
        geography=["uruguay", "latin_america"],
        granularity="contracting_process",
        roles=["latin_american_procurement_shape", "process_depth", "supplier_process_shape"],
        quality="mixed",
    ),
    DatasetSourceSpec(
        source_id="thailand_bma_ocds",
        title="Thailand Bangkok Metropolitan Administration via OCP Data Registry",
        provider="Bangkok Metropolitan Administration via Open Contracting Partnership",
        access_url="https://data.open-contracting.org/en/publication/158",
        domains=["procurement", "award", "contract"],
        geography=["thailand", "east_asia_pacific"],
        granularity="contracting_process",
        roles=["east_asian_procurement_shape", "process_depth", "supplier_process_shape"],
        quality="mixed",
        caveats=["Party-level analyses should account for publisher-specific duplicate roles."],
    ),
    DatasetSourceSpec(
        source_id="ted_eu",
        title="Tenders Electronic Daily Open Data",
        provider="Publications Office of the European Union",
        access_url="https://data.ted.europa.eu/",
        domains=["procurement", "buyers", "suppliers", "notices", "contracts"],
        geography=["european_union", "europe"],
        granularity="procurement_notice",
        roles=["eu_procurement_shape", "procurement_taxonomy", "notice_complexity"],
        quality="high",
    ),
    DatasetSourceSpec(
        source_id="usaspending_contracts",
        title="USAspending Contract and Award Data",
        provider="U.S. Department of the Treasury",
        access_url="https://api.usaspending.gov/",
        domains=["procurement", "awards", "transactions", "recipients"],
        geography=["united_states", "north_america"],
        granularity="award_and_transaction",
        roles=["us_procurement_shape", "transaction_scale", "recipient_concentration"],
        quality="high",
    ),
    DatasetSourceSpec(
        source_id="sec_edgar_xbrl",
        title="SEC EDGAR XBRL Company Facts",
        provider="U.S. Securities and Exchange Commission",
        access_url="https://data.sec.gov/",
        domains=["financial_statements", "filings", "public_companies"],
        geography=["united_states", "global_issuers"],
        granularity="company_fact_period",
        roles=["financial_ratios", "balance_sheet_constraints", "revenue_scale"],
        quality="high",
        caveats=["Public-company distributions should not be used unadjusted for SMEs."],
    ),
    DatasetSourceSpec(
        source_id="un_comtrade",
        title="UN Comtrade",
        provider="United Nations Statistics Division",
        access_url="https://comtradeplus.un.org/",
        domains=["trade", "products", "partners", "imports", "exports"],
        geography=["global"],
        granularity="country_product_partner_period",
        roles=["trade_mix", "product_mix", "cross_border_partner_mix"],
        quality="high",
        caveats=["Aggregate trade flows are not firm-level shipment records."],
    ),
    DatasetSourceSpec(
        source_id="online_retail_ii",
        title="UCI Online Retail II",
        provider="UCI Machine Learning Repository",
        access_url="https://archive.ics.uci.edu/dataset/502/online+retail+ii",
        domains=["sales", "transactions", "customers", "products", "cancellations"],
        geography=["united_kingdom", "international_customers"],
        granularity="invoice_line",
        roles=[
            "transaction_shape",
            "line_item_shape",
            "customer_repeat_behavior",
            "cancellation_shape",
        ],
        quality="high_for_narrow_domain",
        caveats=[
            "Single UK non-store retailer; weight only in retail/wholesale profiles.",
            "Missing customer IDs require explicit handling.",
        ],
    ),
    DatasetSourceSpec(
        source_id="enron_email",
        title="Enron Email Dataset",
        provider="CALO / Carnegie Mellon University distribution",
        access_url="https://www.cs.cmu.edu/~enron/",
        domains=["email", "business_communications"],
        geography=["united_states"],
        granularity="email_message",
        roles=["communication_volume", "thread_shape", "message_length", "recipient_shape"],
        quality="use_for_style_only",
        caveats=[
            "Single-company and historically specific corpus.",
            "Do not use corpus content as operational ground truth.",
            "Use only for communication-form statistics and rendering calibration.",
        ],
    ),
)


class FusionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    source_id: str
    region: RegionGroup = RegionGroup.GLOBAL
    industry: IndustryFamily = IndustryFamily.GENERIC
    weight: float = Field(default=1.0, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _weighted_quantile(
    observations: list[FusionObservation],
    q: float,
    *,
    balance_sources: bool,
) -> float:
    if not observations:
        raise ValueError("cannot calculate quantile of empty observations")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between zero and one")

    source_counts = Counter(item.source_id for item in observations)
    weighted = []
    for item in observations:
        weight = item.weight
        if balance_sources:
            # Each publisher contributes the same total mass for this metric regardless of row
            # count. This avoids a large jurisdiction silently becoming the global distribution.
            weight /= source_counts[item.source_id]
        weighted.append((item.value, weight))
    weighted.sort(key=lambda item: item[0])
    total = sum(weight for _, weight in weighted)
    target = q * total
    running = 0.0
    for value, weight in weighted:
        running += weight
        if running >= target:
            return value
    return weighted[-1][0]


class FusionAccumulator:
    """Accumulates normalized observations and emits provenance-bearing profiles."""

    def __init__(self) -> None:
        self._observations: list[FusionObservation] = []

    @property
    def observations(self) -> tuple[FusionObservation, ...]:
        return tuple(self._observations)

    def add(self, observation: FusionObservation) -> None:
        self._observations.append(observation)

    def extend(self, observations: Iterable[FusionObservation]) -> None:
        self._observations.extend(observations)

    def build_profile(
        self,
        *,
        profile_id: str,
        region: RegionGroup = RegionGroup.GLOBAL,
        industry: IndustryFamily = IndustryFamily.GENERIC,
        size_band: CompanySizeBand = CompanySizeBand.MEDIUM,
        minimum_observations: int = 20,
        fallback: CalibrationProfile | None = None,
        balance_sources: bool = False,
    ) -> CalibrationProfile:
        buckets: dict[str, list[FusionObservation]] = defaultdict(list)
        for observation in self._observations:
            region_match = observation.region in {RegionGroup.GLOBAL, region}
            industry_match = observation.industry in {IndustryFamily.GENERIC, industry}
            if region_match and industry_match:
                buckets[observation.metric].append(observation)

        distributions: dict[str, QuantileDistribution] = {}
        used_sources: set[str] = set()
        empirical_count = 0
        for metric, observations in buckets.items():
            if len(observations) < minimum_observations:
                continue
            used_sources.update(item.source_id for item in observations)
            empirical_count += len(observations)
            values = [item.value for item in observations]
            distributions[metric] = QuantileDistribution(
                minimum=min(values),
                p10=_weighted_quantile(observations, 0.10, balance_sources=balance_sources),
                p50=_weighted_quantile(observations, 0.50, balance_sources=balance_sources),
                p90=_weighted_quantile(observations, 0.90, balance_sources=balance_sources),
                maximum=max(values),
                observation_count=len(observations),
                source_ids=sorted({item.source_id for item in observations}),
            )

        state = "empirical"
        notes: list[str] = []
        categories: dict[str, WeightedCategory] = {}
        if balance_sources and empirical_count:
            notes.append(
                "Empirical quantiles are source-balanced so each publisher contributes equal total weight per metric."
            )
        if fallback is not None:
            missing = set(fallback.distributions) - set(distributions)
            for metric in missing:
                distributions[metric] = fallback.distributions[metric]
            categories = dict(fallback.categories)
            if missing:
                state = "hybrid" if empirical_count else "bootstrap_prior"
                notes.append(
                    "Metrics without sufficient observations were inherited from the bootstrap prior."
                )

        return CalibrationProfile(
            profile_id=profile_id,
            region=region,
            industry=industry,
            size_band=size_band,
            source_ids=sorted(used_sources),
            distributions=distributions,
            categories=categories,
            empirical_observation_count=empirical_count,
            state=state,
            notes=notes,
        )


def build_bootstrap_calibration(
    *,
    region: RegionGroup = RegionGroup.GLOBAL,
    industry: IndustryFamily = IndustryFamily.GENERIC,
    size_band: CompanySizeBand = CompanySizeBand.MEDIUM,
) -> CalibrationProfile:
    """Return conservative priors while the empirical fusion corpus is being materialized.

    These numbers are deliberately marked `bootstrap_prior`; they are not represented as
    measurements from the registered sources. The compiler records this state in every world.
    """

    employee_ranges = {
        CompanySizeBand.MICRO: (5, 7, 9, 15, 20),
        CompanySizeBand.SMALL: (10, 18, 35, 70, 100),
        CompanySizeBand.MEDIUM: (50, 90, 220, 650, 1000),
        CompanySizeBand.LARGE: (250, 700, 2500, 8000, 20_000),
        CompanySizeBand.ENTERPRISE: (1000, 5000, 20_000, 70_000, 150_000),
    }
    e = employee_ranges[size_band]

    return CalibrationProfile(
        profile_id=f"bootstrap-{region}-{industry}-{size_band}",
        region=region,
        industry=industry,
        size_band=size_band,
        source_ids=[],
        state="bootstrap_prior",
        distributions={
            "firm.employee_count": QuantileDistribution(
                minimum=e[0], p10=e[1], p50=e[2], p90=e[3], maximum=e[4], unit="employees"
            ),
            "procurement.vendors_per_100_employees": QuantileDistribution(
                minimum=8, p10=18, p50=55, p90=160, maximum=450, unit="vendors/100 employees"
            ),
            "procurement.purchase_orders_per_employee_year": QuantileDistribution(
                minimum=0.4, p10=1.2, p50=4.5, p90=16.0, maximum=45.0, unit="PO/employee/year"
            ),
            "procurement.po_amount_usd": QuantileDistribution(
                minimum=25, p10=180, p50=2800, p90=45_000, maximum=2_500_000, unit="USD"
            ),
            "procurement.receipt_lag_days": QuantileDistribution(
                minimum=0.2, p10=1.0, p50=6.0, p90=28.0, maximum=120.0, unit="days"
            ),
            "finance.invoice_lag_days": QuantileDistribution(
                minimum=0.0, p10=0.5, p50=4.0, p90=18.0, maximum=90.0, unit="days"
            ),
            "finance.payment_lag_days": QuantileDistribution(
                minimum=0.2, p10=5.0, p50=28.0, p90=65.0, maximum=180.0, unit="days"
            ),
            "controls.approval_limit_usd": QuantileDistribution(
                minimum=500, p10=2500, p50=15_000, p90=100_000, maximum=1_000_000, unit="USD"
            ),
            "communications.emails_per_employee_day": QuantileDistribution(
                minimum=0.5, p10=2.0, p50=8.0, p90=28.0, maximum=75.0, unit="messages/day"
            ),
        },
        categories={
            "procurement.payment_terms": WeightedCategory(
                weights={
                    "NET_7": 0.08,
                    "NET_15": 0.17,
                    "NET_30": 0.48,
                    "NET_45": 0.13,
                    "NET_60": 0.14,
                },
                source_ids=[],
            ),
            "organization.department_mix": WeightedCategory(
                weights={
                    "operations": 0.30,
                    "sales": 0.18,
                    "finance": 0.12,
                    "procurement": 0.08,
                    "warehouse": 0.12,
                    "technology": 0.08,
                    "people": 0.06,
                    "legal_compliance": 0.06,
                },
                source_ids=[],
            ),
        },
        notes=[
            "Bootstrap numeric priors are conservative engineering priors and are not claimed as measured source statistics.",
            "The registered source corpus is a research/acquisition plan until observations are materialized into a profile.",
            "Replace bootstrap metrics with empirical or hybrid profile distributions before production benchmark release.",
        ],
    )


def ingest_numeric_csv(
    path: str | Path,
    *,
    source_id: str,
    metric_columns: dict[str, str],
    region: RegionGroup = RegionGroup.GLOBAL,
    industry: IndustryFamily = IndustryFamily.GENERIC,
) -> list[FusionObservation]:
    """Normalize numeric columns from a prepared source extract.

    This deliberately expects an explicit column mapping; silently guessing source schemas
    would make calibration non-reproducible.
    """

    observations: list[FusionObservation] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            for metric, column in metric_columns.items():
                raw = row.get(column)
                if raw in {None, ""}:
                    continue
                try:
                    value = float(str(raw).replace(",", ""))
                except ValueError:
                    continue
                observations.append(
                    FusionObservation(
                        metric=metric,
                        value=value,
                        source_id=source_id,
                        region=region,
                        industry=industry,
                        metadata={"row": row_number, "column": column},
                    )
                )
    return observations


def ingest_ocds_jsonl(
    path: str | Path,
    *,
    source_id: str,
    region: RegionGroup = RegionGroup.GLOBAL,
) -> list[FusionObservation]:
    """Extract robust structural procurement metrics from OCDS compiled releases.

    Currency amounts and dates are intentionally excluded at this layer unless separately
    normalized and quality-checked. Structural counts are emitted only when the underlying
    collection is populated: in OCDS, an absent/empty field often means non-publication rather
    than a measured zero, and treating missingness as zero materially biases the profile.
    """

    observations: list[FusionObservation] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            tender = record.get("tender")
            metrics: dict[str, int] = {}

            if isinstance(tender, dict):
                tenderers = tender.get("tenderers")
                if isinstance(tenderers, list) and tenderers:
                    metrics["procurement.tenderer_count"] = len(tenderers)
                items = tender.get("items")
                if isinstance(items, list) and items:
                    metrics["procurement.items_per_tender"] = len(items)

            awards = record.get("awards")
            if isinstance(awards, list) and awards:
                metrics["procurement.awards_per_process"] = len(awards)

            contracts = record.get("contracts")
            if isinstance(contracts, list) and contracts:
                metrics["procurement.contracts_per_process"] = len(contracts)

            parties = record.get("parties")
            if isinstance(parties, list) and parties:
                metrics["procurement.parties_per_process"] = len(parties)

            for metric, value in metrics.items():
                observations.append(
                    FusionObservation(
                        metric=metric,
                        value=float(value),
                        source_id=source_id,
                        region=region,
                        metadata={"line": line_number},
                    )
                )
    return observations


def source_registry_payload() -> dict[str, Any]:
    return {
        "format": "veritas-operational-world-fusion-v1",
        "sources": [source.model_dump(mode="json") for source in DEFAULT_SOURCES],
    }
