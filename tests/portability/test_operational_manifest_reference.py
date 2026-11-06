from __future__ import annotations

import json

from investigation_world.portability import (
    PortableCapability,
    PortableEnvironmentManifest,
    PortableOperationalContractReference,
    PortableReleaseIdentity,
    PortableResetContract,
    PortableSplit,
    PortableTask,
    PortableTasksetManifest,
    PortableVerifierContract,
    PortableVisibility,
)


def _manifest() -> PortableEnvironmentManifest:
    return PortableEnvironmentManifest(
        environment_id="fixture.environment",
        environment_version="v1",
        sku="Fixture",
        domain="fixture",
        description="fixture",
        visibility=PortableVisibility.BUYER_SAFE,
        release=PortableReleaseIdentity(
            candidate_id="candidate",
            candidate_version="v1",
            evidence_manifest_id="evidence",
            qualification_report_id="report",
            panel_id="panel",
            private_release_manifest_id="private-release",
        ),
        taskset=PortableTasksetManifest(
            taskset_version="v1",
            visible_tasks=[
                PortableTask(
                    task_id="task-1",
                    split=PortableSplit.DEV,
                    seed=7,
                    agent_payload={"prompt": "fixture"},
                    content_digest="digest",
                    verifier_reference="verifier",
                )
            ],
        ),
        capabilities=[PortableCapability(capability_id="submit", description="submit")],
        reset=PortableResetContract(reset_semantics="deterministic fixture reset"),
        verifier=PortableVerifierContract(
            verifier_id="verifier",
            description="fixture verifier",
        ),
    )


def test_unbound_manifest_serialization_preserves_legacy_shape() -> None:
    manifest = _manifest()
    payload = manifest.model_dump(mode="json")

    assert "operational_contract" not in payload
    assert "operational_contract" not in manifest.model_dump_json()
    assert PortableEnvironmentManifest.model_validate(payload).manifest_id == manifest.manifest_id


def test_manifest_binds_only_public_operational_contract_identity() -> None:
    legacy = _manifest()
    payload = legacy.model_dump(mode="json")
    payload["manifest_id"] = ""
    payload["operational_contract"] = {
        "schema_version": "1.0.0",
        "public_contract_id": "poc-public-fixture",
    }

    bound = PortableEnvironmentManifest.model_validate(payload)

    assert bound.operational_contract == PortableOperationalContractReference(
        schema_version="1.0.0",
        public_contract_id="poc-public-fixture",
    )
    assert bound.manifest_id != legacy.manifest_id
    serialized = json.dumps(bound.model_dump(mode="json"), sort_keys=True)
    assert "poc-public-fixture" in serialized
    assert '"contract_id"' not in serialized
