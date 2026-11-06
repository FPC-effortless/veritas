from pathlib import Path

WORKFLOW = Path(".github/workflows/portability-validation.yml")


def _external_steps() -> tuple[str, dict[str, str]]:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  external-adapter-contracts:\n", 1)[1]
    job = job.split("  sealed-sre-portability:\n", 1)[0]
    steps = {}
    for block in job.split("      - name: ")[1:]:
        name, body = block.split("\n", 1)
        steps[name] = body
    return job, steps


def test_external_sdks_run_in_separate_runner_environments() -> None:
    job, steps = _external_steps()
    assert "adapter: [hud, prime]" in job
    assert "fail-fast: false" in job
    for adapter, step_name, requirement, other in (
        ("hud", "Install current HUD SDK", "hud>=0.6,<0.7", "verifiers"),
        ("prime", "Install current Prime SDK", "verifiers>=0.2,<0.3", "hud"),
    ):
        step = steps[step_name]
        assert f"if: matrix.adapter == '{adapter}'" in step
        assert requirement in step
        assert other not in step
        assert "python -m pip check" in step
        assert "python -c" in step


def test_each_adapter_retains_its_smoke_and_protocol_checks() -> None:
    _, steps = _external_steps()
    for adapter, names in (
        (
            "hud",
            (
                "Load generated HUD package against current SDK API",
                "Build generated HUD protocol image",
                "Exercise HUD task start and grade protocol",
            ),
        ),
        (
            "prime",
            (
                "Load generated Prime package against current SDK API",
                "Build and load public Prime Hub package",
                "Exercise Prime v1 and legacy compatibility entrypoints",
            ),
        ),
    ):
        for name in names:
            assert f"if: matrix.adapter == '{adapter}'" in steps[name]
        smoke = steps[names[0]]
        assert "python -m pytest" in smoke
        assert f"::test_generated_{adapter}_package_clean_installs" in smoke
    assert "if:" not in steps["Generate deterministic external fixture packages"]
