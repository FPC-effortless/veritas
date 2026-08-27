from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    QuantileDistribution,
    RegionGroup,
    WeightedCategory,
)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("cannot calculate quantile from no values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _distribution(
    values: Iterable[float],
    *,
    source_id: str,
    unit: str = "",
) -> QuantileDistribution:
    finite = [float(value) for value in values]
    if not finite:
        raise ValueError("distribution requires at least one value")
    return QuantileDistribution(
        minimum=min(finite),
        p10=_quantile(finite, 0.10),
        p50=_quantile(finite, 0.50),
        p90=_quantile(finite, 0.90),
        maximum=max(finite),
        unit=unit,
        observation_count=len(finite),
        source_ids=[source_id],
    )


def _category(counter: Counter[str], *, source_id: str) -> WeightedCategory:
    if not counter:
        raise ValueError("categorical distribution requires at least one observation")
    return WeightedCategory(
        weights={key: float(value) for key, value in sorted(counter.items())},
        observation_count=sum(counter.values()),
        source_ids=[source_id],
    )


def build_gleif_entity_profile(
    records: Iterable[dict[str, Any]],
    *,
    profile_id: str = "global-entity-gleif-v1",
    source_id: str = "gleif_lei",
) -> CalibrationProfile:
    """Build global, size-agnostic legal-entity shape calibration from GLEIF records."""

    jurisdiction: Counter[str] = Counter()
    entity_status: Counter[str] = Counter()
    registration_status: Counter[str] = Counter()
    legal_form: Counter[str] = Counter()
    other_name_counts: list[float] = []
    legal_address_lines: list[float] = []
    headquarters_address_lines: list[float] = []
    record_count = 0

    for record in records:
        attributes = record.get("attributes") or {}
        entity = attributes.get("entity") or {}
        registration = attributes.get("registration") or {}
        record_count += 1

        if value := entity.get("jurisdiction"):
            jurisdiction[str(value)] += 1
        if value := entity.get("status"):
            entity_status[str(value)] += 1
        if value := registration.get("status"):
            registration_status[str(value)] += 1
        form = entity.get("legalForm") or {}
        if value := form.get("id"):
            legal_form[str(value)] += 1

        other_names = entity.get("otherNames") or []
        transliterated = entity.get("transliteratedOtherNames") or []
        other_name_counts.append(float(len(other_names) + len(transliterated)))
        legal_address_lines.append(
            float(len((entity.get("legalAddress") or {}).get("addressLines") or []))
        )
        headquarters_address_lines.append(
            float(len((entity.get("headquartersAddress") or {}).get("addressLines") or []))
        )

    if record_count == 0:
        raise ValueError("GLEIF profile requires at least one LEI record")

    categories: dict[str, WeightedCategory] = {}
    if jurisdiction:
        categories["organization.legal_jurisdiction"] = _category(
            jurisdiction, source_id=source_id
        )
    if entity_status:
        categories["organization.entity_status"] = _category(
            entity_status, source_id=source_id
        )
    if registration_status:
        categories["organization.lei_registration_status"] = _category(
            registration_status, source_id=source_id
        )
    if legal_form:
        categories["organization.legal_form_code"] = _category(legal_form, source_id=source_id)

    return CalibrationProfile(
        profile_id=profile_id,
        region=RegionGroup.GLOBAL,
        industry=IndustryFamily.GENERIC,
        # Required schema anchor only; `size_scope=agnostic` is authoritative.
        size_band=CompanySizeBand.MEDIUM,
        size_scope="agnostic",
        source_ids=[source_id],
        distributions={
            "organization.other_names_count": _distribution(
                other_name_counts, source_id=source_id, unit="names/entity"
            ),
            "organization.legal_address_lines": _distribution(
                legal_address_lines, source_id=source_id, unit="lines/entity"
            ),
            "organization.headquarters_address_lines": _distribution(
                headquarters_address_lines, source_id=source_id, unit="lines/entity"
            ),
        },
        categories=categories,
        empirical_observation_count=record_count,
        state="empirical",
        notes=[
            "GLEIF calibrates legal-entity form, status, jurisdiction and address shape only.",
            "LEI coverage is not interpreted as a representative census of all firms or SMEs.",
            "Entity-shape metrics are size-agnostic; they do not imply identical entity prevalence across size bands.",
        ],
    )


def _frame_map(payload: dict[str, Any], *, us_only: bool = True) -> dict[int, float]:
    values: dict[int, float] = {}
    for item in payload.get("data") or []:
        location = str(item.get("loc") or "")
        if us_only and location and not location.startswith("US"):
            continue
        cik = item.get("cik")
        value = item.get("val")
        if cik is None or value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric < 0:
            continue
        values[int(cik)] = numeric
    return values


def build_sec_financial_profile(
    *,
    assets: dict[str, Any],
    liabilities: dict[str, Any],
    accounts_payable: dict[str, Any],
    revenues: dict[str, Any],
    profile_id: str = "north-america-public-company-finance-large-v1",
    source_id: str = "sec_edgar_xbrl",
) -> CalibrationProfile:
    """Build large-company finance calibration from SEC XBRL cross-company frames."""

    assets_by_cik = _frame_map(assets)
    liabilities_by_cik = _frame_map(liabilities)
    payables_by_cik = _frame_map(accounts_payable)
    revenues_by_cik = _frame_map(revenues)

    asset_values = [value for value in assets_by_cik.values() if value > 0]
    revenue_values = [value for value in revenues_by_cik.values() if value > 0]
    payable_values = [value for value in payables_by_cik.values() if value > 0]

    liabilities_to_assets: list[float] = []
    payable_to_assets: list[float] = []
    revenue_to_assets: list[float] = []
    for cik, asset_value in assets_by_cik.items():
        if asset_value <= 0:
            continue
        if cik in liabilities_by_cik:
            ratio = liabilities_by_cik[cik] / asset_value
            if 0 <= ratio <= 5:
                liabilities_to_assets.append(ratio)
        if cik in payables_by_cik:
            ratio = payables_by_cik[cik] / asset_value
            if 0 <= ratio <= 1.5:
                payable_to_assets.append(ratio)
        if cik in revenues_by_cik:
            ratio = revenues_by_cik[cik] / asset_value
            if 0 <= ratio <= 20:
                revenue_to_assets.append(ratio)

    distributions: dict[str, QuantileDistribution] = {}
    if asset_values:
        distributions["finance.assets_usd"] = _distribution(
            asset_values, source_id=source_id, unit="USD"
        )
    if revenue_values:
        distributions["finance.annual_revenue_usd"] = _distribution(
            revenue_values, source_id=source_id, unit="USD/year"
        )
    if payable_values:
        distributions["finance.accounts_payable_usd"] = _distribution(
            payable_values, source_id=source_id, unit="USD"
        )
    if liabilities_to_assets:
        distributions["finance.liabilities_to_assets"] = _distribution(
            liabilities_to_assets, source_id=source_id, unit="ratio"
        )
    if payable_to_assets:
        distributions["finance.accounts_payable_to_assets"] = _distribution(
            payable_to_assets, source_id=source_id, unit="ratio"
        )
    if revenue_to_assets:
        distributions["finance.revenue_to_assets"] = _distribution(
            revenue_to_assets, source_id=source_id, unit="ratio"
        )
    if not distributions:
        raise ValueError("SEC frames did not produce any admissible financial observations")

    return CalibrationProfile(
        profile_id=profile_id,
        region=RegionGroup.NORTH_AMERICA,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.LARGE,
        size_scope="exact",
        source_ids=[source_id],
        distributions=distributions,
        empirical_observation_count=sum(
            distribution.observation_count for distribution in distributions.values()
        ),
        state="empirical",
        notes=[
            "SEC XBRL frames calibrate large/public-company finance only; do not apply raw scale to SMEs.",
            "Ratio quality gates remove impossible/extreme cross-tag matches before quantile construction.",
        ],
    )


def build_retail_transaction_profile(
    invoices: Iterable[dict[str, Any]],
    *,
    customer_invoice_counts: Iterable[int] = (),
    country_counts: Counter[str] | None = None,
    profile_id: str = "europe-retail-transactions-v1",
    source_id: str = "online_retail_ii",
) -> CalibrationProfile:
    """Build medium retail transaction-shape calibration from invoice aggregates."""

    rows = list(invoices)
    if not rows:
        raise ValueError("retail profile requires invoice aggregates")

    line_counts = [float(item["line_count"]) for item in rows if item.get("line_count")]
    unique_products = [
        float(item["unique_products"]) for item in rows if item.get("unique_products")
    ]
    completed_values = [
        float(item["value_gbp"])
        for item in rows
        if not item.get("cancelled") and float(item.get("value_gbp", 0.0)) > 0
    ]
    customer_counts = [float(value) for value in customer_invoice_counts if value > 0]
    status = Counter("cancelled" if item.get("cancelled") else "completed" for item in rows)

    distributions: dict[str, QuantileDistribution] = {
        "sales.line_items_per_invoice": _distribution(
            line_counts, source_id=source_id, unit="lines/invoice"
        ),
        "sales.unique_products_per_invoice": _distribution(
            unique_products, source_id=source_id, unit="products/invoice"
        ),
    }
    if completed_values:
        distributions["sales.invoice_value_gbp"] = _distribution(
            completed_values, source_id=source_id, unit="GBP"
        )
    if customer_counts:
        distributions["sales.invoices_per_customer_observed_period"] = _distribution(
            customer_counts, source_id=source_id, unit="invoices/customer"
        )

    categories = {"sales.invoice_status": _category(status, source_id=source_id)}
    if country_counts:
        categories["sales.customer_country"] = _category(country_counts, source_id=source_id)

    return CalibrationProfile(
        profile_id=profile_id,
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.RETAIL,
        size_band=CompanySizeBand.MEDIUM,
        size_scope="exact",
        source_ids=[source_id],
        distributions=distributions,
        categories=categories,
        empirical_observation_count=len(rows),
        state="empirical",
        notes=[
            "Online Retail II calibrates retail invoice/customer/product shape for a narrow UK non-store retailer.",
            "Use only in retail/wholesale-adjacent worlds; do not generalize its monetary scale to unrelated industries.",
        ],
    )
