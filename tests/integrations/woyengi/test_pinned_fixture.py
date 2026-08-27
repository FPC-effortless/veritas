from __future__ import annotations

import hashlib
from pathlib import Path

from investigation_world.integrations.woyengi import adapt_pinned_world_bundle_fixture


PINNED_SHA256 = "3577aa29266dac59921c31e65d22ad657c4b7a9191011e9f5448aed32781e10b"
FIXTURE = Path(__file__).parent / "fixtures" / "veritas-adapter-v0.1.json"


def test_upstream_pinned_fixture_bytes_match_woyengi_issue_9_hash():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINNED_SHA256


def test_pinned_fixture_preserves_public_and_private_semantics_losslessly():
    episode = adapt_pinned_world_bundle_fixture(
        FIXTURE.read_bytes(),
        expected_sha256=PINNED_SHA256,
    )

    assert episode.task.objective == "Activate supplier 42 only after verified finance approval."
    assert episode.task.permitted_systems == ["system:approval-workflow", "system:supplier-records"]

    actions = {action.name: action for action in episode.task.available_actions}
    request = actions["world-action:request-approval"]
    assert request.system == "system:approval-workflow"
    assert request.parameter_names == ["requested_role", "supplier_id"]
    assert request.cost == 1
    assert request.description == "request_approval"

    evidence = {record.record_id: record for record in episode.records}["evidence:approval-decision"]
    assert evidence.system == "system:approval-workflow"
    assert evidence.record_type == "approval-decision"
    assert evidence.fields["decision"] == "approved"
    assert "evidence:approval-decision" in episode.oracle.required_evidence_ids

    assert episode.oracle.target_state[0].key() == "supplier.status"
    invariant = episode.oracle.invariants[0]
    assert invariant.invariant_id == "evaluator-invariant:approval-ledger-consistency"
    assert invariant.assertion.key() == "approval.signerRole"
    assert invariant.severity == "critical"
    assert invariant.scope == "always"

    effect = episode.oracle.action_effects[0]
    assert effect.action_name == "world-action:request-approval"
    assert effect.set_state == {
        "approval.signerRole": "finance-approver",
        "approval.status": "approved",
    }
    assert effect.observable_result["evidenceId"] == "evidence:approval-decision"

    # Exact raw-fixture provenance is evaluator-side only because the full hash binds
    # evaluator-private bytes. It must never become policy-visible metadata.
    assert episode.oracle.source_fixture_sha256 == PINNED_SHA256
    assert PINNED_SHA256 not in str(episode.public_payload())
