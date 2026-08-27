from __future__ import annotations

from pathlib import Path

from investigation_world.commercial.sre_evaluation import build_sre_prompt
from investigation_world.commercial.sre_release import SealedSRERelease, load_sealed_sre_release
from investigation_world.foundry.models import stable_hash
from investigation_world.portability.identity import portable_task_id
from investigation_world.portability.models import (
    PortableCapability,
    PortableEnvironmentManifest,
    PortableReleaseIdentity,
    PortableResetContract,
    PortableSplit,
    PortableTask,
    PortableTasksetManifest,
    PortableVerifierContract,
    PortableVisibility,
)
from investigation_world.portability.validation import require_portable_manifest
from investigation_world.qualification import QualificationSplit

SRE_PORTABLE_ENVIRONMENT_ID = "veritas.sre.causal-classification"
SRE_PORTABLE_SKU = "Veritas SRE Evaluation Pack v1"
SRE_PORTABLE_VERIFIER_ID = "veritas.sre.causal-classification.verifier"


def _portable_split(split: QualificationSplit) -> PortableSplit:
    return PortableSplit(split.value)


def _task_seed(public_digest: str) -> int:
    return int(stable_hash({"public_digest": public_digest})[:16], 16)


def _portable_task(release: SealedSRERelease, scenario_index: int) -> PortableTask:
    scenario = release.candidate.scenarios[scenario_index]
    seed = _task_seed(scenario.public_digest)
    task_id = portable_task_id(
        environment_id=SRE_PORTABLE_ENVIRONMENT_ID,
        environment_version=release.candidate.version,
        source_digest=scenario.public_digest,
        split=scenario.split.value,
        seed=seed,
    )
    return PortableTask(
        task_id=task_id,
        split=_portable_split(scenario.split),
        seed=seed,
        agent_payload={"prompt": build_sre_prompt(scenario.normalized_text)},
        content_digest=scenario.public_digest,
        capability_tags=["incident-response", "causal-classification", "sre"],
        source_group_digest=stable_hash({"source_group_id": scenario.source_group_id}),
        verifier_reference=SRE_PORTABLE_VERIFIER_ID,
        metadata={"source_identity_exposed": False, "ground_truth_exposed": False},
    )


def build_sre_portable_manifest(
    qualification_path: Path,
    *,
    visibility: PortableVisibility = PortableVisibility.BUYER_SAFE,
    public_sample_limit: int = 8,
    source_bundle_sha256: str | None = None,
    expected_candidate_id: str | None = None,
    expected_evidence_manifest_id: str | None = None,
    expected_report_id: str | None = None,
    expected_panel_id: str | None = None,
    expected_private_release_manifest_id: str | None = None,
) -> PortableEnvironmentManifest:
    if public_sample_limit < 0:
        raise ValueError("public_sample_limit must be non-negative")

    release = load_sealed_sre_release(
        qualification_path,
        expected_candidate_id=expected_candidate_id,
        expected_evidence_manifest_id=expected_evidence_manifest_id,
        expected_report_id=expected_report_id,
        expected_panel_id=expected_panel_id,
        expected_private_release_manifest_id=expected_private_release_manifest_id,
    )

    release_identity = PortableReleaseIdentity(
        candidate_id=release.candidate.candidate_id,
        candidate_version=release.candidate.version,
        evidence_manifest_id=release.candidate.evidence_manifest.manifest_id,
        qualification_report_id=release.qualification.report_id,
        panel_id=release.qualification.panel_id,
        private_release_manifest_id=release.private_release_manifest.manifest_id,
        source_bundle_sha256=source_bundle_sha256,
    )

    indexed = list(enumerate(release.candidate.scenarios))
    public_candidates = [
        (index, scenario)
        for index, scenario in indexed
        if scenario.split != QualificationSplit.PRIVATE_TEST
    ]
    private_candidates = [
        (index, scenario)
        for index, scenario in indexed
        if scenario.split == QualificationSplit.PRIVATE_TEST
    ]

    if visibility == PortableVisibility.PRIVATE_OPERATOR:
        selected = sorted(indexed, key=lambda item: item[1].public_digest)
        private_ids_included = True
    else:
        selected = sorted(public_candidates, key=lambda item: item[1].public_digest)[:public_sample_limit]
        private_ids_included = False

    visible_tasks = [_portable_task(release, index) for index, _ in selected]
    taskset = PortableTasksetManifest(
        taskset_version=release.candidate.version,
        visible_tasks=visible_tasks,
        private_task_count=len(private_candidates),
        private_task_ids_included=private_ids_included,
        private_ground_truth_included=False,
    )

    manifest = PortableEnvironmentManifest(
        environment_id=SRE_PORTABLE_ENVIRONMENT_ID,
        environment_version=release.candidate.version,
        sku=SRE_PORTABLE_SKU,
        domain=release.candidate.domain,
        description=(
            "Portable projection of the exact sealed Veritas SRE causal-classification release. "
            "Agent-visible tasks contain early incident evidence only; private causal truth remains "
            "behind the canonical deterministic verifier boundary."
        ),
        visibility=visibility,
        release=release_identity,
        taskset=taskset,
        capabilities=[
            PortableCapability(
                capability_id="submit_causal_classification",
                description="Submit one allowed causal class for the active incident task.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "causal_class": {
                            "type": "string",
                            "enum": ["regression", "infrastructure", "capacity", "transient"],
                        }
                    },
                    "required": ["causal_class"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"accepted": {"type": "boolean"}},
                    "required": ["accepted"],
                },
            )
        ],
        reset=PortableResetContract(
            reset_semantics=(
                "The active task is reconstructed solely from immutable release identity, portable "
                "task identity, and seed. Repeated resets must reproduce verifier-relevant state."
            )
        ),
        verifier=PortableVerifierContract(
            verifier_id=SRE_PORTABLE_VERIFIER_ID,
            description=(
                "Deterministically scores the submitted causal class against sealed private ground "
                "truth without exposing that truth in buyer-safe task payloads."
            ),
        ),
        adapters=["hud", "prime-verifiers-v1", "prime-load-environment-compat"],
        dependencies=["investigation-world>=0.10,<0.12"],
        provenance={
            "source": "sealed-veritas-qualification-release",
            "scientifically_qualified": release.qualification.releaseable,
            "qualification_gate_count": len(release.qualification.gates),
            "failed_qualification_gates": [
                gate.name for gate in release.qualification.gates if not gate.passed
            ],
            "private_case_details_included": visibility == PortableVisibility.PRIVATE_OPERATOR,
            "private_ground_truth_included": False,
        },
        licensing={
            "environment_code": "repository-license",
            "source_evidence": "provenance-governed",
            "private_release": "commercial-restricted",
        },
    )
    return require_portable_manifest(manifest)
