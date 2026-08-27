from pathlib import Path


def test_core_contract_has_no_provider_specific_vocabulary() -> None:
    root = Path(__file__).parents[2] / "src" / "investigation_world" / "sandbox"
    core = (root / "models.py").read_text() + (root / "protocol.py").read_text()
    lowered = core.lower()
    for provider in ("daytona", "modal", "docker", "kubernetes"):
        assert provider not in lowered
