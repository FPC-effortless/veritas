from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_do_not_build_policy_names_all_presumptive_non_goals() -> None:
    policy = (ROOT / "docs/architecture/do-not-build-policy.md").read_text(encoding="utf-8")

    for required in (
        "full reinforcement-learning trainer",
        "model-serving platform",
        "hyperscale sandbox cloud",
        "generic human/expert marketplace",
        "benchmark aggregator",
        "largest harness catalog",
        "generic agent framework",
        "replacement for supported target runtimes",
        "integration is insufficient",
        "falsify",
    ):
        assert required in policy


def test_architecture_proposals_require_integration_and_identity_evidence() -> None:
    issue_template = (
        ROOT / ".github/ISSUE_TEMPLATE/architecture-proposal.yml"
    ).read_text(encoding="utf-8")
    pull_request_template = (ROOT / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )

    for field in ("id: integrations", "id: insufficiency", "id: identity", "id: falsifiers"):
        assert field in issue_template
    assert "why integration is insufficient" in pull_request_template
    assert "Qualification level actually established" in pull_request_template


def test_authorized_dispatch_is_main_only_and_excludes_release_and_training() -> None:
    workflow = (ROOT / ".github/workflows/authorized-dispatch.yml").read_text(
        encoding="utf-8"
    )

    assert 'github.event.issue.title == \'Veritas automation control\'' in workflow
    assert '["OWNER", "MEMBER", "COLLABORATOR"]' in workflow
    assert 'gh workflow run "$TARGET_WORKFLOW"' in workflow
    assert "--ref main" in workflow
    assert 'workflow="portability-validation.yml"' in workflow
    assert "release.yml" not in workflow
    assert "training-value" not in workflow
    assert "model-calibration" not in workflow
