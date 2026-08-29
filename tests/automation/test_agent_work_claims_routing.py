from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")


def test_supported_recovery_commands_are_routed_to_the_serialized_coordinator() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "startsWith(github.event.comment.body, '/recover ')" in workflow
    assert "startsWith(github.event.comment.body, '/recover-metadata ')" in workflow
    assert "github.event.comment.body == '/roadmap-bootstrap'" in workflow
    assert "github.event.issue.pull_request == null" in workflow
    assert "group: agent-work-coordination" in workflow
    assert "cancel-in-progress: false" in workflow
