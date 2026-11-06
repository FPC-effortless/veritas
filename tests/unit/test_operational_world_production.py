from __future__ import annotations

from investigation_world.operational_world import (
    CompanySizeBand,
    IndustryFamily,
    OperationalWorldCompiler,
    OperationalWorldSpec,
    RegionGroup,
)
from investigation_world.operational_world.external_profiles import (
    build_gleif_entity_profile,
    build_sec_financial_profile,
)


def test_partial_size_agnostic_profile_is_completed_with_explicit_bootstrap() -> None:
    gleif = build_gleif_entity_profile(
        [
            {
                "attributes": {
                    "entity": {
                        "jurisdiction": "NG",
                        "status": "ACTIVE",
                        "legalForm": {"id": "8888"},
                        "otherNames": [],
                        "transliteratedOtherNames": [],
                        "legalAddress": {"addressLines": ["Example Road"]},
                        "headquartersAddress": {"addressLines": ["Example Road"]},
                    },
                    "registration": {"status": "ISSUED"},
                }
            }
        ]
    )
    compiler = OperationalWorldCompiler(calibration=gleif)
    world = compiler.compile(
        OperationalWorldSpec(
            seed=210,
            region=RegionGroup.AFRICA,
            industry=IndustryFamily.LOGISTICS,
            size_band=CompanySizeBand.LARGE,
            employee_count=300,
            simulation_days=14,
        )
    )

    assert world.calibration.state == "hybrid"
    assert "gleif_lei" in world.calibration.source_ids
    assert "organization.other_names_count" in world.calibration.distributions
    assert "procurement.po_amount_usd" in world.calibration.distributions
    assert world.calibration.distributions["organization.other_names_count"].observation_count == 1
    assert world.calibration.distributions["procurement.po_amount_usd"].observation_count == 0


def test_sec_finance_creates_coherent_calibrated_snapshot() -> None:
    profile = build_sec_financial_profile(
        assets={"data": [{"cik": 1, "val": 1000.0, "loc": "US-CA"}]},
        liabilities={"data": [{"cik": 1, "val": 600.0, "loc": "US-CA"}]},
        accounts_payable={"data": [{"cik": 1, "val": 100.0, "loc": "US-CA"}]},
        revenues={"data": [{"cik": 1, "val": 1500.0, "loc": "US-CA"}]},
    )
    compiler = OperationalWorldCompiler(calibration=profile)
    world = compiler.compile(
        OperationalWorldSpec(
            seed=211,
            region=RegionGroup.NORTH_AMERICA,
            industry=IndustryFamily.GENERIC,
            size_band=CompanySizeBand.LARGE,
            employee_count=300,
            simulation_days=14,
        )
    )

    snapshots = [record for record in world.records if record.record_type == "financial_snapshot"]
    assert len(snapshots) == 1
    fields = snapshots[0].fields
    assert round(fields["liabilities_usd"] + fields["equity_usd"], 2) == fields["assets_usd"]
    assert fields["accounts_payable_usd"] <= fields["liabilities_usd"]
    assert fields["annual_revenue_usd"] > 0
    assert world.metadata["financial_snapshot_calibrated"] is True
