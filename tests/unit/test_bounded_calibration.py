from investigation_world.calibration.bounded import run_bounded_calibration


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
