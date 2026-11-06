from collections import Counter

from investigation_world.gold10 import build_task, build_taskset
from investigation_world.investigation_data.gold10_manifest import build_gold10_manifest


def test_gold10_taskset_preserves_frozen_case_and_split_contract() -> None:
    tasks = build_taskset()
    assert len(tasks) == 10
    assert Counter(task.split for task in tasks) == Counter(
        {"train": 6, "dev": 2, "eval": 2}
    )
    assert len({task.case_id for task in tasks}) == 10
    assert len({task.task.task_id for task in tasks}) == 10

    manifest = build_gold10_manifest()
    assert {task.case_id for task in tasks} == {
        row["case_id"] for row in manifest["cases"]
    }
    assert all(row["controlled_private_truth_available"] is False for row in manifest["cases"])
    assert all(row["report"]["eligible_for_task_evidence"] is True for row in manifest["cases"])


def test_gold10_tasks_expose_only_temporally_available_public_evidence() -> None:
    tasks = build_taskset()
    modalities = {
        evidence.modality
        for task in tasks
        for evidence in task.available_evidence
    }
    assert len(modalities) >= 2
    assert all(task.available_evidence for task in tasks)
    for task in tasks:
        available_ids = {evidence.evidence_id for evidence in task.available_evidence}
        assert set(task.task.target_refs) == available_ids
        assert task.task.constraints["no_hindsight"] is True
        assert task.task.constraints["institutional_findings_are_not_private_truth"] is True
        for finding in task.available_findings:
            assert set(finding.source_evidence_ids).issubset(available_ids)


def test_texas_city_temporal_cut_withholds_later_csb_material() -> None:
    task = build_task("2005-04-I-TX")
    ids = {item.evidence_id for item in task.available_evidence}
    assert "csb-preliminary-findings-2005-10-27" in ids
    assert "csb-organizational-findings-2006-10-30" not in ids
    assert "csb-final-findings-release-2007-03-20" not in ids
    assert "csb-anatomy-of-a-disaster-2008-03-21" not in ids


def test_chevron_remains_the_frozen_calibration_case() -> None:
    tasks = {task.case_id: task for task in build_taskset()}
    calibration = {
        case_id for case_id, task in tasks.items() if task.calibration_required
    }
    assert calibration == {"2012-03-I-CA"}
