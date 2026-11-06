from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import (
    CorpusCaseSpec,
    CorpusEvidenceRelease,
    FusionCorpusIndex,
    corpus_digest,
    load_fusion_corpus,
    validate_fusion_corpus_sources,
)

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = (
    ROOT / "docs" / "investigation_data" / "corpora" / "csb_gold_10" / "index.json"
)
TEXAS_CITY_MANIFEST = (
    ROOT
    / "docs"
    / "investigation_data"
    / "pilots"
    / "csb_texas_city_2005"
    / "manifest.json"
)


def load_index() -> FusionCorpusIndex:
    return load_fusion_corpus(INDEX_PATH)


def test_csb_gold_10_is_valid_and_catalog_bound() -> None:
    index = load_index()
    validate_fusion_corpus_sources(index, load_catalog())

    assert index.corpus_id == "csb-gold-10"
    assert index.source_id == "uscsb"
    assert index.target_cases == 10
    assert len(index.cases) == 10
    assert index.date_only_availability_policy == "next_day_12z"
    assert len(corpus_digest(index)) == 64


def test_csb_gold_10_has_unique_cases_and_temporal_diversity() -> None:
    index = load_index()
    case_ids = {case.case_id for case in index.cases}
    releases = [release for case in index.cases for release in case.evidence_releases]

    assert len(case_ids) == 10
    assert "2005-04-I-TX" in case_ids
    assert "2008-03-I-FL" in case_ids
    assert "2008-05-I-GA" in case_ids
    assert "2010-08-I-WA" in case_ids
    assert "2012-03-I-CA" in case_ids
    assert "2013-02-I-TX" in case_ids
    assert "2013-03-I-LA" in case_ids
    assert "2017-08-I-TX" in case_ids
    assert "2018-02-I-WI" in case_ids
    assert "2019-04-I-PA" in case_ids
    assert sum(item.phase == "pre_final" for item in releases) >= 5
    assert sum(item.phase == "post_final" for item in releases) >= 5


def test_csb_gold_10_covers_distinct_investigative_capabilities() -> None:
    tags = {tag for case in load_index().cases for tag in case.capability_tags}

    assert {
        "reactive-chemistry",
        "combustible-dust",
        "metallurgy",
        "corrosion",
        "emergency-response",
        "extreme-weather",
        "turnaround",
        "hydrofluoric-acid",
    } <= tags


def test_csb_gold_10_release_dates_are_case_consistent() -> None:
    for case in load_index().cases:
        assert case.accident_date <= case.final_report_date
        for release in case.evidence_releases:
            assert release.release_date >= case.accident_date
            if release.phase == "pre_final":
                assert release.release_date < case.final_report_date
            if release.phase == "post_final":
                assert release.release_date > case.final_report_date


def test_csb_gold_10_links_to_existing_texas_city_pilot() -> None:
    assert TEXAS_CITY_MANIFEST.is_file()
    texas_city = next(case for case in load_index().cases if case.case_id == "2005-04-I-TX")

    assert texas_city.slug == "bp-texas-city-2005"
    assert "Anatomy of a Disaster" in texas_city.evidence_releases[0].title


def test_corpus_source_validation_rejects_off_allowlist_host() -> None:
    index = load_index()
    first_case = index.cases[0]
    bad_release = first_case.evidence_releases[0].model_copy(
        update={"url": "https://example.com/video"}
    )
    bad_case = first_case.model_copy(update={"evidence_releases": (bad_release,)})
    bad_index = index.model_copy(update={"cases": (bad_case, *index.cases[1:])})

    with pytest.raises(ValueError, match="outside source"):
        validate_fusion_corpus_sources(bad_index, load_catalog())


def test_corpus_case_rejects_mislabeled_pre_final_release() -> None:
    release = CorpusEvidenceRelease(
        release_id="late-preliminary",
        title="Late preliminary artifact",
        release_date=date(2020, 1, 3),
        modality="video",
        phase="pre_final",
        role="visual_reconstruction",
        url="https://www.csb.gov/videos/example/",
    )

    with pytest.raises(ValueError, match="not before final report"):
        CorpusCaseSpec(
            case_id="2020-01-I-TX",
            slug="invalid-case",
            title="Invalid case",
            location="Texas",
            accident_date=date(2020, 1, 1),
            final_report_date=date(2020, 1, 2),
            investigation_url="https://www.csb.gov/example/",
            capability_tags=("testing",),
            evidence_releases=(release,),
        )
