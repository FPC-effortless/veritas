"""Validate canonical producers: public Gold-10 symptoms and synthetic native execution."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from investigation_world.capability_science.diagnostics import (
    ingest_capability_failure,
    ingest_failure_family,
)
from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience.diagnostics import (
    failure_family_candidates,
    intervention_failure_families,
)
from investigation_world.experience_foundry.admission import PublicTrainingRecorder
from investigation_world.gold10 import reference_submission, traceable_experience
from investigation_world.operational.models import EpisodeSubmission


def contrast(root, formula="=0"):
    recorder = PublicTrainingRecorder(root / "source")
    records = recorder.runtime.public_payload()["records"]
    audit = next(row for row in records if row["record_type"] == "formula_audit")
    recorder.act("repair_formula", cell=audit["object_id"], formula=formula)
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Constructed public TRAIN protocol",
            evidence_ids=[
                r["record_id"]
                for r in records
                if r["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    receipt = execute_counterfactual_experience(
        source,
        branch_step=0,
        replacement={
            "cell": audit["object_id"],
            "formula": f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})",
        },
        artifact_root=root / "branches",
    )
    return receipt, source


def gold_sources():
    # Gold-10 public fixture files are external data, not wheel contents.
    root = Path(os.environ.get("VERITAS_TEST_FIXTURE_ROOT", Path(__file__).resolve().parents[2]))
    return tuple(
        traceable_experience(
            case,
            reference_submission(case, root=root).model_copy(update={"evidence_ids": ()}),
            root=root,
        )
        for case in ("2005-04-I-TX", "2012-03-I-CA")
    )


def test_gold_failure_family_ingestion_keeps_unknown_capability_and_full_evidence():
    sources = gold_sources()
    candidate = failure_family_candidates(sources)[0]
    evidence = ingest_failure_family(candidate, sources=sources)
    assert evidence.candidate == candidate
    assert evidence.capability_mapping == "UNKNOWN"
    assert evidence.capability_spec is None
    assert evidence.frequency_scope == "distinct_source_experiences_not_population_rate"
    assert evidence.causal_qualification == "UNKNOWN"
    assert evidence.source_digests.keys() == set(candidate.family.member_experience_ids)
    assert evidence == ingest_failure_family(candidate, sources=tuple(reversed(sources)))
    assert evidence.buyer_safe_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    with pytest.raises(ValueError, match="candidate|source"):
        ingest_failure_family(candidate, sources=sources[:1])
    modified = candidate.model_copy(
        update={"family": candidate.family.model_copy(update={"severity": 0.1})}
    )
    assert modified.family.family_id == candidate.family.family_id
    with pytest.raises(ValueError, match="candidate"):
        ingest_failure_family(modified, sources=sources)


def test_capability_gap_ingestion_revalidates_source_receipt_and_full_digest(tmp_path):
    sources = (contrast(tmp_path / "a"), contrast(tmp_path / "b", "=1"))
    candidate = intervention_failure_families(sources)[0]
    evidence = ingest_capability_failure(candidate, sources=sources)
    assert evidence.candidate == candidate
    assert evidence.capability_spec.contract == sources[0][1].capability
    assert len(evidence.capability_spec.contract_digest) == 64
    assert evidence.capability_mapping == "DECLARED_TASK_ASSOCIATION"
    assert evidence.evidence_status == "OBSERVED_BOUND_TASK_FAILURES"
    assert evidence.causal_qualification == "UNKNOWN"
    assert evidence.frequency_scope == "distinct_recorded_protocols_not_independent_agents"
    assert evidence.severity_scope == "normalized_unmet_target_fraction_not_general_harm"
    assert evidence.candidate.gap.frequency == 2
    assert len(evidence.receipt_digests) == 2
    assert evidence == ingest_capability_failure(candidate, sources=tuple(reversed(sources)))
    assert sources[0][1].experience.experience_id not in str(evidence.public_payload())
    assert str(tmp_path) not in str(evidence.public_payload())

    modified = candidate.model_copy(
        update={"gap": candidate.gap.model_copy(update={"frequency": 100})}
    )
    assert modified.gap.gap_id == candidate.gap.gap_id
    with pytest.raises(ValueError, match="candidate"):
        ingest_capability_failure(modified, sources=sources)
    with pytest.raises(ValueError):
        ingest_capability_failure(candidate, sources=((sources[0][0], sources[1][1]), sources[1]))
    new_contract = sources[0][1].capability.model_copy(
        update={"objective": "name unchanged, contents forged"}
    )
    forged = replace(sources[0][1], capability=new_contract)
    with pytest.raises(ValueError):
        ingest_capability_failure(candidate, sources=((sources[0][0], forged), sources[1]))


def test_full_wrapper_identity_changes_even_when_legacy_statistics_ids_do_not(tmp_path):
    sources = (contrast(tmp_path / "a"), contrast(tmp_path / "b", "=1"))
    candidate = intervention_failure_families(sources)[0]
    evidence = ingest_capability_failure(candidate, sources=sources)
    payload = evidence.model_dump(mode="python")
    payload["candidate"]["gap"]["frequency"] = 3
    with pytest.raises(ValueError, match="identity"):
        type(evidence).model_validate(payload)
    with pytest.raises(ValueError, match="identity"):
        evidence.model_copy(update={"receipt_digests": {"forged": "a" * 64}}).public_payload()


def test_missing_artifacts_do_not_become_an_unknown_but_accepted_candidate(tmp_path):
    import shutil

    sources = (contrast(tmp_path / "a"), contrast(tmp_path / "b", "=1"))
    candidate = intervention_failure_families(sources)[0]
    shutil.rmtree(tmp_path / "a" / "branches")
    with pytest.raises(ValueError):
        ingest_capability_failure(candidate, sources=sources)
