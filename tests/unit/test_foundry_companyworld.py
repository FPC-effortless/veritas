from pathlib import Path

from investigation_world.foundry import (
    DistributionSplit,
    companyworld_capability_contract,
    companyworld_task_metadata,
    default_companyworld_build_plan,
    patched_generator_source,
)


class FakeEpisode:
    world_id = "companyworld:ORG-1:142"

    def public_payload(self):
        return {
            "world_id": self.world_id,
            "task": {
                "task_id": "O2C-1",
                "world_id": self.world_id,
                "task_type": "O2C_FULFILLMENT_TIMING",
                "permitted_systems": ["ERP", "WMS"],
                "available_actions": ["EXPEDITE_ORDER"],
                "max_actions": 5,
                "constraints": {},
            },
            "records": [
                {"record_id":"R1","object_id":"SO-1","system":"ERP","record_type":"order","fields":{}},
                {"record_id":"R2","object_id":"SHP-1","system":"WMS","record_type":"shipment","fields":{}},
            ],
        }


def test_companyworld_task_ids_are_world_scoped():
    metadata = companyworld_task_metadata(
        FakeEpisode(), split=DistributionSplit.OOD, taskset_version="cw-v1",
        harness_version="react-v1", runtime_version="companyworld-v1", seed=142,
    )
    assert metadata.task_id == "companyworld:ORG-1:142::O2C-1"
    assert metadata.generator_parameters["companyworld_local_task_id"] == "O2C-1"
    assert metadata.generator_parameters["companyworld_world_id"] == "companyworld:ORG-1:142"
    assert "temporal" in metadata.capability_tags
    assert "act" in metadata.capability_tags
    assert metadata.difficulty.tools == 2
    assert metadata.difficulty.entities == 2
    assert metadata.difficulty.steps == 5


def test_unknown_world_keeps_local_task_id_for_synthetic_fixtures():
    class NoWorld:
        def public_payload(self):
            return {"task":{"task_id":"LOCAL-1","task_type":"UNKNOWN"},"records":[]}
    metadata = companyworld_task_metadata(
        NoWorld(), split=DistributionSplit.TRAIN, taskset_version="t",
        harness_version="h", runtime_version="r", seed=1,
    )
    assert metadata.task_id == "LOCAL-1"


def test_capability_contract_includes_recovery_and_unseen_seed_transfer():
    contract = companyworld_capability_contract()
    assert "recover" in contract.subcapabilities
    assert "unseen CompanyWorld seeds" in contract.transfer_targets


def test_default_world_plan_uses_disjoint_seeds_and_scale_shift(tmp_path: Path):
    generator = tmp_path / "generate.py"
    generator.write_text("# placeholder")
    plan = default_companyworld_build_plan(generator, tmp_path / "worlds")
    assert [item.seed for item in plan.builds] == [42, 43, 142, 242]
    assert len({item.seed for item in plan.builds}) == 4
    ood = next(item for item in plan.builds if item.split == DistributionSplit.OOD)
    assert ood.profile == "scale_shift"
    assert ood.overrides["N_SALES_ORDERS"] == 65000


def test_generator_patching_rewrites_seed_root_company_and_scale(tmp_path: Path):
    source = '''from pathlib import Path\nSEED=42\nroot=Path('/mnt/data/companyworld_v0_1')\nN_EMP=2500\nN_CUSTOMERS=20000\nN_SUPPLIERS=1200\nN_PRODUCTS=75000\nN_SALES_ORDERS=50000\nTARGET_REVENUE=4500000000.0\nCOMPANY_ID='ORG-000001'\nzip_path='/mnt/data/companyworld_v0_1.zip'\n'''
    plan = default_companyworld_build_plan(tmp_path / "g.py", tmp_path / "worlds")
    ood = next(item for item in plan.builds if item.split == DistributionSplit.OOD)
    patched = patched_generator_source(source, ood)
    assert "SEED = 142" in patched
    assert "ORG-OOD-000001" in patched
    assert "N_EMP = 3200" in patched
    assert "N_SALES_ORDERS = 65000" in patched
    assert str(ood.output_root) in patched
