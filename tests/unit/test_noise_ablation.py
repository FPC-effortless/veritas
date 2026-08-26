from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy, ProjectionTrustPolicy
from investigation_world.calibration.fixtures import diagnostic_fixture
from investigation_world.calibration.noise_ablation import perturb_public_payload
from investigation_world.companyworld.verifier import verify_companyworld


def test_noise_ablation_preserves_public_reference_solution():
    reference = PublicEvidenceReferencePolicy()
    for episode in diagnostic_fixture():
        payload = perturb_public_payload(episode.public_payload(), distractor_count=6)
        result = reference(payload)
        assert verify_companyworld(result, episode).overall_reward == 1.0
        assert len(payload["records"]) >= len(episode.records) + 6


def test_conflicting_projection_does_not_become_valid_evidence():
    projection_trust = ProjectionTrustPolicy()
    saw_projection = False
    for episode in diagnostic_fixture():
        payload = perturb_public_payload(episode.public_payload(), distractor_count=0)
        projections = [item for item in payload["records"] if item["record_type"] == "system_projection"]
        if not projections:
            continue
        saw_projection = True
        result = projection_trust(payload)
        assert verify_companyworld(result, episode).overall_reward == 0.0
    assert saw_projection
