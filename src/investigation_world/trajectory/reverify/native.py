"""Evaluator-only native receipt binding and non-materializing offline inspection."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from investigation_world.foundry.models import stable_hash
from investigation_world.operational.artifacts import (
    NativeArtifactVerification,
    _hash_path,
    native_artifact_descriptor,
)
from investigation_world.operational.models import OperationalEpisode, WorldDomain
from investigation_world.operational.native_submission import (
    NATIVE_ARTIFACT_SOURCES,
    NATIVE_VERIFIER_ID,
    NATIVE_VERIFIER_VERSION,
    NativeSubmissionReceipt,
    native_source_identities,
)
from investigation_world.operational.parameterized_artifacts import (
    ParameterizedNativeArtifactWorkspace,
)
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract.compiler import compile_operational_episode
from investigation_world.trajectory.models import TrajectoryV2, VisibilityClass, canonical_hash

if TYPE_CHECKING:
    from investigation_world.trajectory.reverify.models import OperationalReplayEvidence


def requires_native_evidence(evidence: OperationalReplayEvidence) -> bool:
    public = evidence.portable_contract.public
    return bool(
        public.task_metadata.get("native_artifact")
        or public.episode_metadata.get("native_artifact_profile")
        or any(key.startswith("native_artifact.") for key in evidence.final_state)
        or any(
            a.object_id == "native_artifact"
            for a in evidence.portable_contract.private.semantic_state.target_assertions
        )
    )


def validate_native_submission(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    receipt = evidence.native_submission
    events = [
        event
        for event in trajectory.events
        if event.event_type == "native_submission"
        or event.payload.get("method") == "verify_native_artifact"
    ]
    if receipt is None:
        if requires_native_evidence(evidence) or events:
            raise ValueError("NATIVE_SUBMISSION_EVIDENCE_MISSING")
        return
    # Reparse even model instances: frozen models do not make model_copy(update=...) safe.
    receipt = NativeSubmissionReceipt.model_validate(receipt.model_dump(mode="json"))
    if len(events) != 1:
        raise ValueError("EXACT_NATIVE_TRANSITION_REQUIRED")
    event = events[0]
    index = trajectory.events.index(event)
    if (
        event.event_type != "native_submission"
        or event.payload != {"method": "verify_native_artifact", "receipt_id": receipt.receipt_id}
        or event.visibility is not VisibilityClass.EVALUATOR_PRIVATE
        or event.cost != 0
        or index + 1 >= len(trajectory.events)
        or trajectory.events[index + 1].payload.get("method") != "submit"
        or any(e.payload.get("method") in {"act", "submit"} for e in trajectory.events[index + 2 :])
    ):
        raise ValueError("NATIVE_TRANSITION_ORDER_OR_IDENTITY_INVALID")
    episode = OperationalEpisode.model_validate_json(receipt.episode_json)
    if compile_operational_episode(episode) != evidence.portable_contract:
        raise ValueError("NATIVE_EPISODE_CONTRACT_MISMATCH")
    if (
        stable_hash(evidence.initial_state) != evidence.initial_state_digest
        or stable_hash(evidence.final_state) != evidence.final_state_digest
    ):
        raise ValueError("NATIVE_STATE_CONTENT_DIGEST_MISMATCH")
    comparisons = (
        (json.loads(receipt.initial_state_json), evidence.initial_state),
        (json.loads(receipt.final_state_json), evidence.final_state),
        (
            json.loads(receipt.action_events_json),
            [item.model_dump(mode="json") for item in evidence.action_events],
        ),
        (json.loads(receipt.submission_json), evidence.submission.model_dump(mode="json")),
        (receipt.tool_calls, evidence.tool_calls),
        (receipt.cost_spent, evidence.cost_spent),
    )
    if any(left != right for left, right in comparisons):
        raise ValueError("NATIVE_RECEIPT_REPLAY_MISMATCH")
    # Re-execute the ordinary transition rules without touching native artifacts.
    # Search/read charges are retained in the receipt; actions must be a valid subset.
    replay = OperationalRuntime(episode.model_copy(deep=True))
    replay.state = json.loads(receipt.initial_state_json)
    for action in evidence.action_events:
        replay.act(action.action_name, **action.parameters)
    if replay.events != list(evidence.action_events):
        raise ValueError("NATIVE_ACTION_REPLAY_MISMATCH")
    if replay.budget.calls > evidence.tool_calls or replay.budget.spent > evidence.cost_spent:
        raise ValueError("NATIVE_ACTION_BUDGET_MISMATCH")
    state = replay.state_snapshot()
    if state != json.loads(receipt.pre_state_json):
        raise ValueError("NATIVE_PRE_STATE_MISMATCH")
    verification = NativeArtifactVerification.model_validate_json(receipt.verification_json)
    state.update({f"native_artifact.{key}": value for key, value in verification.checks.items()})
    if state != evidence.final_state:
        raise ValueError("NATIVE_FINAL_STATE_MISMATCH")
    if (
        event.state_before is None
        or event.state_before.digest != stable_hash(json.loads(receipt.pre_state_json))
        or event.state_after is None
        or event.state_after.digest != stable_hash(state)
    ):
        raise ValueError("NATIVE_TRANSITION_STATE_MISMATCH")


# Evaluator-private snapshots are deliberately bounded, not a general artifact store.
_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_MAX_SNAPSHOT_ENTRIES = 1024


@contextmanager
def _retained_snapshot(path: Path) -> Iterator[Path]:
    """Read each retained file once, then inspect only a private copy of those bytes.

    A retained workspace may still be writable by its producer. Hashing that live
    path before and after inspection does not bind the bytes the inspector read.
    This snapshot is a byte copy, never regeneration/materialization of an artifact.
    """
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("NATIVE_ARTIFACT_LINK_UNSUPPORTED")
    directory = path.is_dir()
    candidates = path.rglob("*") if directory else iter((path,))
    remaining = _MAX_SNAPSHOT_BYTES
    captured: list[tuple[Path, bytes]] = []
    for index, item in enumerate(candidates):
        if index >= _MAX_SNAPSHOT_ENTRIES:
            raise ValueError("NATIVE_ARTIFACT_SNAPSHOT_LIMIT")
        mode = item.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("NATIVE_ARTIFACT_FILE_TYPE_UNSUPPORTED")
        # Nonblocking/no-follow prevents a changed leaf becoming a FIFO or symlink.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(item, flags), "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("NATIVE_ARTIFACT_FILE_TYPE_UNSUPPORTED")
            if metadata.st_size > remaining:
                raise ValueError("NATIVE_ARTIFACT_SNAPSHOT_LIMIT")
            content = stream.read(remaining + 1)
        if len(content) > remaining:
            raise ValueError("NATIVE_ARTIFACT_SNAPSHOT_LIMIT")
        remaining -= len(content)
        captured.append((item.relative_to(path) if directory else Path(path.name), content))
    if not directory and not captured:
        raise ValueError("NATIVE_ARTIFACT_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="veritas-native-inspect-") as root:
        snapshot = Path(root) / path.name
        if directory:
            snapshot.mkdir()
        for relative, content in captured:
            destination = snapshot / relative if directory else snapshot
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o400)
        yield snapshot


def verify_retained_artifact(receipt: NativeSubmissionReceipt) -> NativeArtifactVerification:
    """Inspect exact retained bytes, never call verify()/materialize() or apply actions."""
    if (
        receipt.verifier_id != NATIVE_VERIFIER_ID
        or receipt.verifier_version != NATIVE_VERIFIER_VERSION
        or receipt.artifact_sources != NATIVE_ARTIFACT_SOURCES
        or native_source_identities() != NATIVE_ARTIFACT_SOURCES
    ):
        raise ValueError("NATIVE_VERIFIER_IDENTITY_MISMATCH")
    episode = OperationalEpisode.model_validate_json(receipt.episode_json)
    descriptor = native_artifact_descriptor(episode)
    if json.loads(receipt.descriptor_json) != descriptor.model_dump(mode="json"):
        raise ValueError("NATIVE_DESCRIPTOR_MISMATCH")
    path = Path(receipt.artifact_path)
    if not path.is_absolute() or not path.exists() or path.name != descriptor.filename:
        raise ValueError("NATIVE_ARTIFACT_UNAVAILABLE")
    recorded = NativeArtifactVerification.model_validate_json(receipt.verification_json)
    with _retained_snapshot(path) as snapshot:
        if _hash_path(snapshot) != recorded.artifact_hash:
            raise ValueError("NATIVE_ARTIFACT_DIGEST_MISMATCH")
        return _inspect_snapshot(episode, snapshot, recorded)


def _inspect_snapshot(
    episode: OperationalEpisode,
    path: Path,
    recorded: NativeArtifactVerification,
) -> NativeArtifactVerification:
    # __init__ creates directories; verify materializes. Neither is an offline reader.
    workspace = object.__new__(ParameterizedNativeArtifactWorkspace)
    workspace.episode = episode
    workspace.path = path
    inspectors = {
        WorldDomain.FINANCIAL_SPREADSHEET: workspace._verify_finance,
        WorldDomain.ENTERPRISE_OPERATIONS: workspace._verify_enterprise,
        WorldDomain.DEVOPS_INCIDENT_RESPONSE: workspace._verify_devops,
        WorldDomain.INVESTIGATION_OSINT: workspace._verify_osint,
        WorldDomain.GIS_OPERATIONS: workspace._verify_gis,
    }
    checks, measurements = inspectors[episode.task.domain]()
    actual = NativeArtifactVerification(
        valid=all(checks.values()),
        checks=checks,
        measurements=measurements,
        artifact_hash=_hash_path(path),
    )
    # Canonical comparison normalizes SQLite tuple rows to JSON lists.
    if canonical_hash(actual) != canonical_hash(recorded):
        raise ValueError("NATIVE_ARTIFACT_CHECK_MISMATCH")
    return actual
