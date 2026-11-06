from __future__ import annotations

from itertools import product
from typing import Any

from investigation_world.observatory.models import (
    CellMatrixSpec,
    ExperimentSpec,
    LongitudinalCell,
)


def materialize_cells(spec: CellMatrixSpec) -> list[LongitudinalCell]:
    cells = [
        LongitudinalCell(
            world=world,
            scenario=scenario,
            model=model,
            harness=harness,
            verifier=verifier,
            execution=execution,
            time_snapshot=time_snapshot,
        )
        for world, scenario, model, harness, verifier, execution, time_snapshot in product(
            spec.worlds,
            spec.scenarios,
            spec.models,
            spec.harnesses,
            spec.verifiers,
            spec.executions,
            spec.time_snapshots,
        )
    ]
    return sorted(cells, key=lambda cell: cell.cell_id)


def experiment_from_matrix(
    name: str,
    spec: CellMatrixSpec,
    *,
    hypothesis: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[ExperimentSpec, list[LongitudinalCell]]:
    cells = materialize_cells(spec)
    experiment = ExperimentSpec(
        name=name,
        hypothesis=hypothesis,
        cell_ids=[cell.cell_id for cell in cells],
        metadata=metadata or {},
    )
    return experiment, cells
