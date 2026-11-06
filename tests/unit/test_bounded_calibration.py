import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from investigation_world.calibration.bounded import run_bounded_calibration
from tools import run_bounded_model_calibration as cli


def test_bounded_profile_measures_only_requested_levels_and_preserves_anchors():
    report = run_bounded_calibration(
        lambda prompt: "{}",
        model_name="empty-test-model",
        levels=("diagnostic", "interactive"),
        episodes_per_level=2,
    )
    assert report["mode"] == "bounded_full_context_plan"
    assert report["levels"] == ["diagnostic", "interactive"]
    assert report["episodes"] == {"diagnostic": 2, "interactive": 2}
    assert set(report["model_scores"]) == {"diagnostic", "interactive"}
    assert report["reference_anchors"]["diagnostic"]["mean"] == 1.0
    assert report["reference_anchors"]["interactive"]["mean"] == 1.0
    # Empty JSON is syntactically valid but not a valid Veritas answer schema,
    # so bounded calibration deliberately counts it as an invalid structured output.
    assert report["parse_failures"] == {"diagnostic": 2, "interactive": 2}


def test_bounded_profile_rejects_unsupported_or_excessive_slices():
    try:
        run_bounded_calibration(lambda _: "{}", model_name="x", levels=("dynamic",))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unsupported levels must fail")

    try:
        run_bounded_calibration(lambda _: "{}", model_name="x", episodes_per_level=4)
    except ValueError as exc:
        assert "between 1 and 3" in str(exc)
    else:
        raise AssertionError("oversized bounded slice must fail")


def test_expensive_bounded_calibration_requires_manual_dispatch():
    workflow = Path(".github/workflows/model-calibration-bounded-strong.yml").read_text()
    triggers = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert triggers.strip() == "workflow_dispatch:"


@pytest.mark.parametrize("version", ["4.43.4", "4.46.3", "4.57.1"])
def test_loader_uses_dtype_keyword_supported_across_transformers4(tmp_path, monkeypatch, version):
    class LoadedModel(Exception):
        pass

    dtype = object()

    def load_model(name, **kwargs):
        assert kwargs["torch_dtype"] is dtype
        assert "dtype" not in kwargs
        raise LoadedModel

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(bfloat16=dtype, float32=object()))
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            __version__=version,
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=load_model),
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *args, **kwargs: object()),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["calibrate", "--model", "fixture/model", "--output", str(tmp_path / "out.json")],
    )
    with pytest.raises(LoadedModel):
        cli.main()
    assert not (tmp_path / "out.json").exists()
