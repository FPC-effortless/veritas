from investigation_world.investigation_data.acquisition import plan_artifact
from investigation_world.investigation_data.catalog import find_source, load_catalog
from investigation_world.investigation_data.models import (
    AcquisitionPolicy,
    AIUsePolicy,
    ArtifactClass,
    ArtifactMethod,
    RedistributionPolicy,
)


def test_cdc_nors_public_policy_is_artifact_scoped() -> None:
    catalog = load_catalog()
    source = find_source(catalog, "cdc-nors-public")

    assert source.rights.acquisition is AcquisitionPolicy.APPROVED
    assert source.rights.redistribution is RedistributionPolicy.REVIEW_REQUIRED
    assert source.rights.redistribution is not RedistributionPolicy.ATTRIBUTION_REQUIRED
    assert source.rights.ai_use is AIUsePolicy.ALLOWED_WITH_CONDITIONS
    assert "5xkq-dg7x" in source.rights.review_notes
    assert "prominent non-endorsement disclaimer" in source.rights.review_notes
    assert "do not substantively alter" in source.rights.review_notes
    assert "available from CDC at no charge" in source.rights.review_notes
    assert source.rights.attribution_required
    assert not source.contains_personal_data
    assert not source.requires_redaction_review

    artifact = source.artifacts[0]
    assert artifact.artifact_id == "nors-5xkq-dg7x"
    assert artifact.method is ArtifactMethod.MANUAL
    assert artifact.artifact_class is ArtifactClass.DATA

    plan = plan_artifact(catalog, source.source_id, artifact.artifact_id)
    assert not plan.allowed
    assert "generic downloader only handles http_file" in plan.reason


def test_uscg_public_acquisition_does_not_imply_ai_or_redistribution_approval() -> None:
    catalog = load_catalog()
    source = find_source(catalog, "uscg-cgmix-iir")

    assert source.rights.acquisition is AcquisitionPolicy.APPROVED
    assert source.rights.redistribution is RedistributionPolicy.REVIEW_REQUIRED
    assert source.rights.ai_use is AIUsePolicy.REVIEW_REQUIRED
    assert source.contains_personal_data
    assert source.requires_redaction_review

    artifact = source.artifacts[0]
    assert artifact.artifact_id == "iir-xlsx-export"
    assert artifact.method is ArtifactMethod.FORM
    assert artifact.artifact_class is ArtifactClass.DATA

    plan = plan_artifact(catalog, source.source_id, artifact.artifact_id)
    assert not plan.allowed
    assert "generic downloader only handles http_file" in plan.reason


def test_blocked_and_unreviewed_rights_remain_fail_closed() -> None:
    catalog = load_catalog()
    blocked = find_source(catalog, "acled")
    uscg = find_source(catalog, "uscg-cgmix-iir")

    assert blocked.rights.acquisition is AcquisitionPolicy.BLOCKED
    assert blocked.rights.redistribution is RedistributionPolicy.BLOCKED
    assert blocked.rights.ai_use is AIUsePolicy.BLOCKED
    assert blocked.artifacts == ()

    assert uscg.rights.redistribution is RedistributionPolicy.REVIEW_REQUIRED
    assert uscg.rights.ai_use is AIUsePolicy.REVIEW_REQUIRED
