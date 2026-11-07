import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.foundry import DistributionSplit
from investigation_world.training_value import (
    build_training_rows,
    build_transfer_suite,
    foundry_transfer,
)
from tools import run_foundry_transfer_training as cli


@pytest.mark.parametrize("version", ["4.46.3", "4.57.1"])
def test_training_loader_uses_supported_transformers4_dtype(tmp_path, monkeypatch, version):
    class LoadedModel(Exception):
        pass

    dtype = object()

    def load_model(name, **kwargs):
        assert kwargs["torch_dtype"] is dtype
        assert "dtype" not in kwargs
        raise LoadedModel

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            float32=dtype,
            manual_seed=lambda seed: None,
            set_num_threads=lambda count: None,
            get_num_threads=lambda: 1,
        ),
    )
    monkeypatch.setitem(
        sys.modules, "peft", SimpleNamespace(LoraConfig=object, get_peft_model=object)
    )
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            __version__=version,
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=load_model),
            AutoTokenizer=SimpleNamespace(
                from_pretrained=lambda *a, **kw: SimpleNamespace(pad_token_id=1)
            ),
        ),
    )
    monkeypatch.setattr("sys.argv", ["train", "--output", str(tmp_path / "out.json")])
    with pytest.raises(LoadedModel):
        cli.main()
    assert not (tmp_path / "out.json").exists()


def test_expensive_transfer_training_requires_manual_dispatch():
    workflow = Path(".github/workflows/training-value-foundry-transfer.yml").read_text()
    triggers = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert triggers.strip() == "workflow_dispatch:"


def test_transfer_suites_are_world_disjoint_and_reference_solvable():
    suites = build_transfer_suite(train_candidates=8, eval_per_split=3)
    world_ids = {
        split: {episode.world_id for episode in episodes} for split, episodes in suites.items()
    }
    assert world_ids["train_pool"] == {"CW-FOUNDRY-TRAIN"}
    assert world_ids["iid"] == {"CW-FOUNDRY-IID"}
    assert world_ids["ood"] == {"CW-FOUNDRY-OOD"}
    assert world_ids["adversarial"] == {"CW-FOUNDRY-ADVERSARIAL"}
    assert len({next(iter(ids)) for ids in world_ids.values()}) == 4

    policy = PublicEvidenceReferencePolicy()
    for split, episodes in suites.items():
        for episode in episodes:
            result = policy(episode.public_payload())
            assert verify_companyworld(result, episode).overall_reward == 1.0, split


def test_ood_and_adversarial_suites_apply_stronger_latent_pressure(monkeypatch):
    samples = []
    materialize = foundry_transfer.materialize_companyworld_task

    def record_parameters(episode, sample):
        samples.append(sample)
        return materialize(episode, sample)

    monkeypatch.setattr(foundry_transfer, "materialize_companyworld_task", record_parameters)
    suites = build_transfer_suite(train_candidates=4, eval_per_split=4)
    iid_records = sum(len(episode.records) for episode in suites["iid"])
    ood_records = sum(len(episode.records) for episode in suites["ood"])
    adversarial_records = sum(len(episode.records) for episode in suites["adversarial"])
    assert ood_records > iid_records
    assert adversarial_records > ood_records
    adversarial = [sample for sample in samples if sample.split == DistributionSplit.ADVERSARIAL]
    assert len(adversarial) == 4
    assert all(sample.difficulty.adversarial_pressure == 1.0 for sample in adversarial)
    for episodes in suites.values():
        for episode in episodes:
            public = json.dumps(episode.public_payload())
            assert "adversarial_pressure" not in public
            assert "latent_difficulty" not in public


def test_training_rows_keep_oracle_private():
    suites = build_transfer_suite(train_candidates=4, eval_per_split=1)
    rows = build_training_rows(suites["train_pool"], target_count=6)
    assert len(rows) == 6
    for row in rows:
        prompt = str(row["prompt"])
        assert "supporting_record_ids" not in prompt
        assert "expected_value" not in prompt
        assert "oracle" not in prompt.casefold()
