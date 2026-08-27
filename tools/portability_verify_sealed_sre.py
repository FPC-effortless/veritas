from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from investigation_world.commercial.sre_release import load_sealed_sre_release
from investigation_world.portability.evidence import build_sre_portable_qualification_evidence
from investigation_world.portability.hud import build_hud_sre_package
from investigation_world.portability.models import PortableVisibility
from investigation_world.portability.prime import build_prime_sre_package
from investigation_world.portability.runtime import SREPortableRuntime
from investigation_world.portability.sre import build_sre_portable_manifest
from investigation_world.portability.sre_private import build_sre_private_portable_tasks
from investigation_world.portability.validation import require_no_forbidden_tokens

_ALLOWED_CAUSAL_CLASSES = ("regression", "infrastructure", "capacity", "transient")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify exact sealed SRE portability without publishing private rows"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-bundle-sha256", required=True)
    parser.add_argument("--expected-candidate-id", required=True)
    parser.add_argument("--expected-evidence-manifest-id", required=True)
    parser.add_argument("--expected-report-id", required=True)
    parser.add_argument("--expected-panel-id", required=True)
    parser.add_argument("--expected-private-release-manifest-id", required=True)
    parser.add_argument("--expected-private-count", type=int, default=30)
    args = parser.parse_args()

    identity_kwargs = {
        "expected_candidate_id": args.expected_candidate_id,
        "expected_evidence_manifest_id": args.expected_evidence_manifest_id,
        "expected_report_id": args.expected_report_id,
        "expected_panel_id": args.expected_panel_id,
        "expected_private_release_manifest_id": args.expected_private_release_manifest_id,
    }
    release = load_sealed_sre_release(args.qualification, **identity_kwargs)
    private_count = len(release.private_release_manifest.private_test_scenario_ids)
    if private_count != args.expected_private_count:
        raise RuntimeError(
            f"sealed private count mismatch: expected {args.expected_private_count}, got {private_count}"
        )

    manifest = build_sre_portable_manifest(
        args.qualification,
        visibility=PortableVisibility.BUYER_SAFE,
        public_sample_limit=8,
        source_bundle_sha256=args.source_bundle_sha256,
        **identity_kwargs,
    )
    evidence = build_sre_portable_qualification_evidence(
        release,
        source_bundle_sha256=args.source_bundle_sha256,
    )
    if evidence.release != manifest.release:
        raise RuntimeError("portable qualification evidence identity differs from manifest identity")

    private_ids = set(release.private_release_manifest.private_test_scenario_ids)
    buyer_safe_material = [
        manifest.model_dump_json(),
        evidence.model_dump_json(),
    ]
    require_no_forbidden_tokens(buyer_safe_material, private_ids)

    private_tasks = build_sre_private_portable_tasks(release)
    if len(private_tasks) != private_count:
        raise RuntimeError("private portable task projection does not match sealed private count")
    private_task_json = [task.model_dump_json() for task in private_tasks]
    require_no_forbidden_tokens(private_task_json, private_ids)

    runtime = SREPortableRuntime(
        environment_version=manifest.environment_version,
        tasks=private_tasks,
    )
    probe = private_tasks[0]
    first_start = runtime.start(probe.task_id, seed=probe.seed, invocation="sealed-proof-a")
    replay = runtime.reset(probe.task_id, seed=probe.seed, invocation="sealed-proof-b")
    if first_start.initial_state_digest != replay.initial_state_digest:
        raise RuntimeError("same sealed task + seed did not reproduce the same initial state")

    correct = runtime.grade(
        first_start,
        json.dumps({"causal_class": probe.expected_causal_class}),
    )
    wrong_class = next(value for value in _ALLOWED_CAUSAL_CLASSES if value != probe.expected_causal_class)
    incorrect = runtime.grade(
        replay,
        json.dumps({"causal_class": wrong_class}),
    )
    if correct.reward != 1.0 or incorrect.reward != 0.0:
        raise RuntimeError("portable runtime reward does not match canonical SRE exact-match semantics")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    first_root = output / "first"
    second_root = output / "second"

    hud_first = build_hud_sre_package(
        first_root / "hud",
        manifest=manifest,
        private_tasks=private_tasks,
        qualification_evidence=evidence,
    )
    prime_first = build_prime_sre_package(
        first_root / "prime",
        manifest=manifest,
        private_tasks=private_tasks,
        qualification_evidence=evidence,
    )
    hud_second = build_hud_sre_package(
        second_root / "hud",
        manifest=manifest,
        private_tasks=private_tasks,
        qualification_evidence=evidence,
    )
    prime_second = build_prime_sre_package(
        second_root / "prime",
        manifest=manifest,
        private_tasks=private_tasks,
        qualification_evidence=evidence,
    )
    if hud_first.package_id != hud_second.package_id:
        raise RuntimeError("HUD package identity is not deterministic")
    if prime_first.package_id != prime_second.package_id:
        raise RuntimeError("Prime package identity is not deterministic")

    summary = {
        "schema_version": "0.11.0",
        "status": "sealed_sre_portability_verified",
        "candidate_id": release.candidate.candidate_id,
        "candidate_version": release.candidate.version,
        "evidence_manifest_id": release.candidate.evidence_manifest.manifest_id,
        "qualification_report_id": release.qualification.report_id,
        "panel_id": release.qualification.panel_id,
        "private_release_manifest_id": release.private_release_manifest.manifest_id,
        "source_bundle_sha256": args.source_bundle_sha256,
        "private_task_count": private_count,
        "portable_manifest_id": manifest.manifest_id,
        "portable_qualification_evidence_id": evidence.evidence_id,
        "hud_package_id": hud_first.package_id,
        "prime_package_id": prime_first.package_id,
        "same_task_seed_same_state": True,
        "canonical_reward_parity": True,
        "private_scenario_ids_in_buyer_safe_material": False,
        "private_scenario_ids_in_operator_task_records": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "buyer_safe_proof.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
