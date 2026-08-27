from __future__ import annotations

from collections import Counter

from investigation_world.operational_world.external_profiles import (
    build_gleif_entity_profile,
    build_retail_transaction_profile,
    build_sec_financial_profile,
)


def test_gleif_builder_keeps_entity_shape_semantics() -> None:
    records = [
        {
            "attributes": {
                "entity": {
                    "jurisdiction": "NG",
                    "status": "ACTIVE",
                    "legalForm": {"id": "8888"},
                    "otherNames": [{"name": "Old Name"}],
                    "transliteratedOtherNames": [],
                    "legalAddress": {"addressLines": ["1 Example Road", "Victoria Island"]},
                    "headquartersAddress": {"addressLines": ["1 Example Road"]},
                },
                "registration": {"status": "ISSUED"},
            }
        },
        {
            "attributes": {
                "entity": {
                    "jurisdiction": "DE",
                    "status": "ACTIVE",
                    "legalForm": {"id": "2HBR"},
                    "otherNames": [],
                    "transliteratedOtherNames": [{"name": "Example AG"}],
                    "legalAddress": {"addressLines": ["Street 2"]},
                    "headquartersAddress": {"addressLines": ["Street 2"]},
                },
                "registration": {"status": "ISSUED"},
            }
        },
    ]

    profile = build_gleif_entity_profile(records)

    assert profile.state == "empirical"
    assert profile.source_ids == ["gleif_lei"]
    assert profile.categories["organization.legal_jurisdiction"].weights == {
        "DE": 1.0,
        "NG": 1.0,
    }
    assert profile.distributions["organization.other_names_count"].observation_count == 2
    assert "firm.employee_count" not in profile.distributions
    assert "finance.assets_usd" not in profile.distributions


def test_sec_builder_joins_by_cik_and_quality_gates_ratios() -> None:
    assets = {
        "data": [
            {"cik": 1, "val": 100.0, "loc": "US-CA"},
            {"cik": 2, "val": 200.0, "loc": "US-NY"},
            {"cik": 3, "val": 100.0, "loc": "GB"},
        ]
    }
    liabilities = {
        "data": [
            {"cik": 1, "val": 60.0, "loc": "US-CA"},
            {"cik": 2, "val": 2000.0, "loc": "US-NY"},  # rejected: ratio > 5
        ]
    }
    payables = {
        "data": [
            {"cik": 1, "val": 10.0, "loc": "US-CA"},
            {"cik": 2, "val": 500.0, "loc": "US-NY"},  # rejected: ratio > 1.5
        ]
    }
    revenues = {
        "data": [
            {"cik": 1, "val": 150.0, "loc": "US-CA"},
            {"cik": 2, "val": 5000.0, "loc": "US-NY"},  # rejected: ratio > 20
        ]
    }

    profile = build_sec_financial_profile(
        assets=assets,
        liabilities=liabilities,
        accounts_payable=payables,
        revenues=revenues,
    )

    assert profile.state == "empirical"
    assert profile.size_band.value == "large"
    assert profile.distributions["finance.liabilities_to_assets"].p50 == 0.6
    assert profile.distributions["finance.accounts_payable_to_assets"].p50 == 0.1
    assert profile.distributions["finance.revenue_to_assets"].p50 == 1.5
    assert profile.distributions["finance.assets_usd"].observation_count == 2


def test_retail_builder_preserves_invoice_and_country_shape() -> None:
    invoices = [
        {"line_count": 3, "unique_products": 2, "value_gbp": 24.0, "cancelled": False},
        {"line_count": 8, "unique_products": 7, "value_gbp": 85.0, "cancelled": False},
        {"line_count": 2, "unique_products": 2, "value_gbp": -15.0, "cancelled": True},
    ]

    profile = build_retail_transaction_profile(
        invoices,
        customer_invoice_counts=[1, 2, 4],
        country_counts=Counter({"United Kingdom": 2, "France": 1}),
    )

    assert profile.state == "empirical"
    assert profile.industry.value == "retail"
    assert profile.categories["sales.invoice_status"].weights == {
        "cancelled": 1.0,
        "completed": 2.0,
    }
    assert profile.categories["sales.customer_country"].weights["United Kingdom"] == 2.0
    assert profile.distributions["sales.invoice_value_gbp"].minimum == 24.0
    assert profile.distributions["sales.line_items_per_invoice"].maximum == 8.0
