from investigation_world.commercial import EvaluationManifest


def test_manifest_omits_none_and_has_stable_public_fields():
    manifest = EvaluationManifest(
        benchmark_version="cw-v1",
        benchmark_hash="abc123",
        model="example-model",
        harness="example-harness",
        attempts_per_task=3,
    )
    payload = manifest.public_payload()
    assert payload["benchmark_version"] == "cw-v1"
    assert payload["benchmark_hash"] == "abc123"
    assert payload["model"] == "example-model"
    assert payload["attempts_per_task"] == 3
    assert "endpoint_host" not in payload
    assert payload["run_id"].startswith("VRUN-")
