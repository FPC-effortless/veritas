"""Cheap adapter checks; real learned-model replay is a separate manual campaign."""

import copy
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("forge_data")
pytest.importorskip("trainlab")

SOURCE = Path(__file__).resolve().parents[2] / (
    "integrations/research_lab/examples/changing_state_replay.py"
)
SPEC = importlib.util.spec_from_file_location("changing_state_replay_test", SOURCE)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def memory():
    return {"keys": ["r0", "r1", "r2", "r3"], "events": [
        {"op": "set", "key": "r0", "value": "v1"},
        {"op": "set", "key": "r0", "value": "v7"},
    ]}


def test_encoder_preserves_history_without_targets():
    prefix = memory()
    before = copy.deepcopy(prefix)
    tokens = [replay.TOKENS[i] for i in replay.encode(prefix, "r0")]
    assert tokens == ["<bos>", "set", "r0", "v1", ";", "set", "r0", "v7", ";",
                      "<nop>", "<nop>", "<nop>", "<nop>", "ask", "r0", "?"]
    assert prefix == before
    assert replay.encode(prefix, "r1")[:-2] == replay.encode(prefix, "r0")[:-2]


@pytest.mark.parametrize("change", ["delete", "copy", "identity", "value", "labels", "keys"])
def test_encoder_rejects_untrained_semantics_and_labels(change):
    prefix = memory()
    if change in {"delete", "copy"}:
        prefix["events"][0]["op"] = change
    elif change == "identity":
        prefix["events"][0]["key"] = "r4"
    elif change == "value":
        prefix["events"][0]["value"] = "v8"
    elif change == "labels":
        prefix["events"][0]["destination_target"] = 0
    else:
        prefix["keys"].append("r4")
    with pytest.raises(ValueError):
        replay.encode(prefix, "r0")


def test_encoder_rejects_unsupported_query():
    with pytest.raises(ValueError):
        replay.encode(memory(), "r4")


def test_corrupt_package_rejected_before_destination_created(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "source.py").write_text("changed source")
    replay.write_json(package / "MANIFEST.json", {
        "files": [{"path": "source.py", "sha256": "0" * 64}]
    })
    destination = tmp_path / "prepared"
    with pytest.raises(ValueError, match="package hash mismatch"):
        replay.prepare_source(package, destination)
    assert not destination.exists()


def test_wrong_csm_archive_rejected_before_destination_created(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    archive = package / "CSM-Research-Update-20261109.zip"
    archive.write_bytes(b"different archive")
    replay.write_json(package / "MANIFEST.json", {
        "files": [{"path": archive.name, "sha256": replay.digest(archive)}]
    })
    destination = tmp_path / "prepared"
    with pytest.raises(ValueError, match="wrong original CSM archive"):
        replay.prepare_source(package, destination)
    assert not destination.exists()
