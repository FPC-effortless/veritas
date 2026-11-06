"""Constructed contracts and controls; these are not measured model capabilities."""

import copy
import json

import pytest

from investigation_world.capability_science.core import (
    CapabilitySpec,
    HypothesisHistory,
    HypothesisRevision,
    PrerequisiteClaim,
    PrerequisiteGraph,
    PrerequisiteIntervention,
)
from investigation_world.experience import ExperienceReference
from investigation_world.foundry.models import CapabilityContract
from investigation_world.observatory.capability_graph import CapabilityGraph
from investigation_world.trajectory import VisibilityClass, canonical_hash

PUBLIC = VisibilityClass.PUBLIC
PRIVATE = VisibilityClass.EVALUATOR_PRIVATE


def ref(name="constructed", visibility=PUBLIC):
    return ExperienceReference(
        reference_id=name,
        reference_type="constructed_test_evidence",
        digest=canonical_hash(name),
        visibility=visibility,
    )


def spec(name="retrieve", **changes):
    return CapabilitySpec(
        contract=CapabilityContract(capability_id=name, objective=f"Constructed {name}", **changes),
        visibility=PUBLIC,
    )


def edge(a, b, **changes):
    return PrerequisiteClaim(
        prerequisite=a.record_id,
        dependent=b.record_id,
        evidence_references=(ref(),),
        visibility=PUBLIC,
        **changes,
    )


def test_spec_binds_all_canonical_contract_material_not_just_name():
    original = spec()
    assert len(original.contract_digest) == 64
    assert original.contract.content_digest.startswith("CCONTRACT-")
    assert original == CapabilitySpec.model_validate_json(original.model_dump_json())
    for field in (
        "success_conditions",
        "failure_conditions",
        "hard_invariants",
        "transfer_targets",
    ):
        changed = spec(**{field: ["changed"]})
        assert changed.record_id != original.record_id
        assert changed.contract_digest != original.contract_digest
    assert spec(version="2").record_id != original.record_id
    assert spec(subcapabilities=["other"]).record_id != original.record_id
    stale = copy.deepcopy(original)
    stale.contract.objective = "Mutated"
    with pytest.raises(ValueError, match="digest|identity"):
        stale.checked()
    with pytest.raises(ValueError):
        stale.public_payload()


def test_graph_wraps_existing_cycle_validation_and_preserves_evidence():
    a, b, c = spec("a"), spec("b"), spec("c")
    graph = PrerequisiteGraph(specs=(a, b, c), claims=(edge(a, b), edge(b, c)), visibility=PUBLIC)
    assert isinstance(graph.observatory_graph(), CapabilityGraph)
    assert graph.claims[0].status == "HYPOTHESIZED"
    assert graph.claims[0].causal_qualification == "UNKNOWN"
    assert graph.public_payload()["claims"][0]["evidence_references"]
    with pytest.raises(ValueError, match="acyclic"):
        PrerequisiteGraph(specs=(a, b, c), claims=(*graph.claims, edge(c, a)))
    with pytest.raises(ValueError, match="unknown node"):
        PrerequisiteGraph(specs=(a,), claims=(edge(a, b),))
    with pytest.raises(ValueError, match="duplicate"):
        PrerequisiteGraph(specs=(a, b), claims=(edge(a, b), edge(a, b)))
    with pytest.raises(ValueError):
        PrerequisiteClaim(prerequisite=a.record_id, dependent=b.record_id, evidence_references=())


def test_observation_cannot_become_intervention_support_or_causal_proof():
    a, b = spec("a"), spec("b")
    observational = edge(a, b, status="OBSERVED_ASSOCIATION")
    with pytest.raises(ValueError, match="intervention"):
        PrerequisiteClaim.model_validate(
            {
                **observational.model_dump(),
                "record_id": "",
                "status": "INTERVENTION_SUPPORT_REPORTED",
            }
        )
    study = PrerequisiteIntervention(
        prerequisite=a.record_id,
        dependent=b.record_id,
        fixed_context_digest=canonical_hash("same model/env/verifier/population/metric"),
        protocol_reference=ref("registered-protocol"),
        with_prerequisite_reference=ref("with"),
        without_prerequisite_reference=ref("without"),
        with_prerequisite_score=0.8,
        without_prerequisite_score=0.3,
        replicates=3,
        visibility=PUBLIC,
    )
    claim = edge(a, b, status="INTERVENTION_SUPPORT_REPORTED", intervention=study)
    assert claim.causal_qualification == "UNKNOWN"
    assert claim.intervention.reported_difference == pytest.approx(0.5)
    for change in (
        {"without_prerequisite_score": 0.9},
        {"prerequisite": b.record_id},
        {"with_prerequisite_reference": ref("without")},
    ):
        with pytest.raises(ValueError):
            bad = PrerequisiteIntervention.model_validate(
                {**study.model_dump(), **change, "record_id": ""}
            )
            edge(a, b, status="INTERVENTION_SUPPORT_REPORTED", intervention=bad)
    with pytest.raises(ValueError):
        edge(a, b, causal_qualification="PASS")


def revision(hypothesis="h1", index=0, previous=None, status="PROPOSED", **changes):
    return HypothesisRevision(
        hypothesis_key=hypothesis,
        revision=index,
        previous_record_id=previous,
        statement="Constructed prerequisite removal lowers target score",
        capability_spec_ids=(spec().record_id,),
        falsifier="No target-score drop with all other conditions fixed",
        status=status,
        evidence_references=() if status == "PROPOSED" else (ref(status),),
        visibility=PUBLIC,
        **changes,
    )


def test_append_only_hypothesis_history_retains_failed_refuted_inconclusive():
    history = HypothesisHistory(specs=(spec(),), revisions=(revision(),), visibility=PUBLIC)
    initial = history.model_dump_json()
    for status in ("FAILED", "REFUTED", "INCONCLUSIVE"):
        prior = history.revisions[-1]
        history = history.append(
            revision(index=prior.revision + 1, previous=prior.record_id, status=status)
        )
    assert [x.status for x in history.revisions] == [
        "PROPOSED",
        "FAILED",
        "REFUTED",
        "INCONCLUSIVE",
    ]
    assert len(json.loads(initial)["revisions"]) == 1
    with pytest.raises(ValueError, match="history|chain|revision"):
        HypothesisHistory(specs=(spec(),), revisions=(history.revisions[0], history.revisions[-1]))
    with pytest.raises(ValueError):
        history.append(revision(index=4, previous="forged", status="FAILED"))
    with pytest.raises(ValueError):
        HypothesisHistory(specs=(spec(),), revisions=(revision(status="SUPPORTED"),))


def test_private_projections_withhold_ids_labels_hashes_and_nested_metadata():
    private = spec("SECRET-LABEL").model_copy(update={"visibility": PRIVATE, "record_id": ""})
    private = private.checked()
    a = spec("a")
    graph = PrerequisiteGraph(specs=(a, private), claims=(edge(a, private),), visibility=PUBLIC)
    safe = graph.buyer_safe_payload()
    assert safe == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert "SECRET" not in json.dumps(safe)
    assert private.record_id not in json.dumps(safe)
    hidden_ref = ref().model_copy(update={"private_metadata": {"secret": "HIDDEN"}})
    hidden = PrerequisiteClaim(
        prerequisite=a.record_id,
        dependent=spec("b").record_id,
        evidence_references=(hidden_ref,),
        visibility=PUBLIC,
    )
    assert hidden.public_payload() == safe
    buyer = (
        spec()
        .model_copy(update={"visibility": VisibilityClass.BUYER_SAFE, "record_id": ""})
        .checked()
    )
    assert buyer.public_payload() == safe
    assert buyer.buyer_safe_payload()["contract"]["capability_id"] == "retrieve"


@pytest.mark.parametrize("bad", ["", "not-a-digest", "a" * 63])
def test_evidence_requires_nonblank_content_bound_references(bad):
    a, b = spec("a"), spec("b")
    with pytest.raises(ValueError):
        PrerequisiteClaim(
            prerequisite=a.record_id,
            dependent=b.record_id,
            evidence_references=(ref().model_copy(update={"digest": bad}),),
        )


def test_hypothesis_registry_resolves_exact_spec_identity_and_rejects_unknown_name():
    with pytest.raises(ValueError, match="capability"):
        HypothesisHistory(specs=(spec("different"),), revisions=(revision(),))
    with pytest.raises(ValueError, match="duplicate"):
        HypothesisHistory(specs=(spec(), spec()), revisions=(revision(),))


def test_revalidation_does_not_rewrite_legacy_reference_metadata_containers():
    reference = ref().model_copy(update={"public_metadata": {"dimensions": ["a", "b"]}})
    claim = PrerequisiteClaim(
        prerequisite=spec("a").record_id,
        dependent=spec("b").record_id,
        evidence_references=(reference,),
    )
    assert claim.evidence_references[0] == reference


def test_derived_prerequisite_difference_revalidates_mutated_record():
    study = PrerequisiteIntervention(
        prerequisite=spec("a").record_id,
        dependent=spec("b").record_id,
        fixed_context_digest="a" * 64,
        protocol_reference=ref("protocol"),
        with_prerequisite_reference=ref("with"),
        without_prerequisite_reference=ref("without"),
        with_prerequisite_score=0.8,
        without_prerequisite_score=0.2,
        replicates=2,
    )
    with pytest.raises(ValueError):
        _ = study.model_copy(update={"with_prerequisite_score": 0.9}).reported_difference
