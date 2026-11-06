from __future__ import annotations

import pytest
from pydantic import ValidationError

from investigation_world.trajectory.audit import (
    MetadataCoverage,
    MetadataFieldCoverage,
    MetadataRequirement,
    ProducerKind,
    ProducerMetadataCoverage,
    TrajectoryMetadataAudit,
    TrajectoryMetadataField,
)

BASE_COMMIT = "fbdb74db7080a078c945506a6c759305f4cd1f78"


def _complete_producer() -> ProducerMetadataCoverage:
    fields = tuple(
        MetadataFieldCoverage(
            field=field,
            requirement=MetadataRequirement.REQUIRED,
            coverage=MetadataCoverage.PRESENT,
            evidence_paths=("tests/fixture.py",),
            detail="fixture preserves the field",
        )
        for field in TrajectoryMetadataField
    )
    return ProducerMetadataCoverage(
        producer_id="complete-fixture",
        producer_kind=ProducerKind.TRAJECTORY_PRODUCER,
        emits_trajectory_v2=True,
        fields=fields,
    )


def test_stale_nested_producer_copy_is_revalidated_by_audit() -> None:
    producer = _complete_producer()
    first = producer.fields[0]
    stale_field = first.model_copy(
        update={
            "coverage": MetadataCoverage.CONDITIONAL,
            "condition": "caller must supply evidence",
        }
    )
    stale_producer = producer.model_copy(
        update={"fields": (stale_field, *producer.fields[1:])}
    )

    with pytest.raises(ValidationError, match="producer completeness"):
        TrajectoryMetadataAudit(
            base_commit_sha=BASE_COMMIT,
            producers=(stale_producer,),
        )
