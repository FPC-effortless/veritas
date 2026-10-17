from investigation_world.gold10_qualification.verifier import (
    buyer_safe_summary,
    compile_gold10_verifier_qualification,
)


def test_buyer_safe_summary_excludes_answer_bearing_material() -> None:
    summary = buyer_safe_summary(compile_gold10_verifier_qualification())
    assert summary["status"] == "PASS"
    assert summary["task_count"] == 10
    rendered = repr(summary)
    for forbidden in (
        "primary_hypothesis",
        "alternative_hypothesis",
        "claims",
        "evidence_ids",
        "statement",
        "fixture_id",
        "payload_sha256",
    ):
        assert forbidden not in rendered
