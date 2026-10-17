from __future__ import annotations

from typing import Any

from .models import Gold10VerifierQualification


def buyer_safe_summary(qualification: Gold10VerifierQualification) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for record in sorted(
        qualification.task_records,
        key=lambda item: item.binding.case_id,
    ):
        tasks.append(
            {
                "case_id": record.binding.case_id,
                "task_id": record.binding.task_id,
                "split": record.binding.split,
                "task_manifest_sha256": record.binding.task_manifest_sha256,
                "record_id": record.record_id,
                "effective_status": record.effective_status.value,
                "generic_report_id": record.report.report_id,
                "metrics": dict(sorted(record.report.metrics.items())),
                "gates": [
                    {
                        "name": gate.name,
                        "outcome": gate.outcome.value,
                    }
                    for gate in record.report.gates
                ],
                "not_applicable_gates": sorted(
                    item.gate
                    for item in record.applicability
                    if item.applicability.value == "NOT_APPLICABLE"
                ),
            }
        )
    return {
        "schema_version": "gold10-verifier-qualification-buyer-safe-v1",
        "qualification_id": qualification.qualification_id,
        "pilot_id": qualification.pilot_id,
        "taskset_version": qualification.taskset_version,
        "verifier_target_contract_sha256": qualification.verifier_target_contract_sha256,
        "status": qualification.status.value,
        "task_count": len(tasks),
        "tasks": tasks,
        "authority": "VERIFIER_VALIDATED_ONLY",
    }
