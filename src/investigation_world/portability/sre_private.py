from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from investigation_world.commercial.sre_evaluation import build_sre_prompt
from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.foundry.models import stable_hash
from investigation_world.portability.identity import portable_task_id
from investigation_world.portability.sre import SRE_PORTABLE_ENVIRONMENT_ID
from investigation_world.qualification import QualificationSplit


class SREPrivatePortableTask(BaseModel):
    """Operator-only record used to build external private evaluation packages.

    This model intentionally contains hidden scoring truth. It must never be embedded in a buyer-safe
    manifest or committed as generated data to the public repository.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    seed: int
    prompt: str
    expected_causal_class: str
    public_digest: str


def _task_seed(public_digest: str) -> int:
    return int(stable_hash({"public_digest": public_digest})[:16], 16)


def build_sre_private_portable_tasks(release: SealedSRERelease) -> list[SREPrivatePortableTask]:
    private_cases = [
        case for case in release.cases if case.scenario.split == QualificationSplit.PRIVATE_TEST
    ]
    sealed_ids = sorted(release.private_release_manifest.private_test_scenario_ids)
    case_ids = sorted(case.scenario.scenario_id for case in private_cases)
    if case_ids != sealed_ids:
        raise RuntimeError("operator private task projection does not match sealed private panel")

    records: list[SREPrivatePortableTask] = []
    for case in sorted(private_cases, key=lambda item: item.scenario.public_digest):
        seed = _task_seed(case.scenario.public_digest)
        records.append(
            SREPrivatePortableTask(
                task_id=portable_task_id(
                    environment_id=SRE_PORTABLE_ENVIRONMENT_ID,
                    environment_version=release.candidate.version,
                    source_digest=case.scenario.public_digest,
                    split=case.scenario.split.value,
                    seed=seed,
                ),
                seed=seed,
                prompt=build_sre_prompt(case.public_text),
                expected_causal_class=case.causal_class.value,
                public_digest=case.scenario.public_digest,
            )
        )
    return records
