from __future__ import annotations

from collections.abc import Iterable

from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    QuantileDistribution,
    RegionGroup,
    WeightedCategory,
)


def _profile_specificity(
    profile: CalibrationProfile,
    *,
    region: RegionGroup,
    industry: IndustryFamily,
    size_band: CompanySizeBand,
) -> tuple[int, int, int]:
    """Return a stable specificity rank for profile conflict resolution."""

    scope = 0
    if profile.region == region and region != RegionGroup.GLOBAL:
        scope += 2
    if profile.industry == industry and industry != IndustryFamily.GENERIC:
        scope += 2
    size_specificity = 1 if profile.size_scope == "exact" and profile.size_band == size_band else 0
    evidence = {"bootstrap_prior": 0, "hybrid": 1, "empirical": 2}[profile.state]
    return scope, size_specificity, evidence


def _validate_source_profile(
    profile: CalibrationProfile,
    *,
    region: RegionGroup,
    industry: IndustryFamily,
    size_band: CompanySizeBand,
) -> None:
    if profile.region not in {RegionGroup.GLOBAL, region}:
        raise ValueError(
            f"profile {profile.profile_id} region {profile.region} is incompatible with {region}"
        )
    if profile.industry not in {IndustryFamily.GENERIC, industry}:
        raise ValueError(
            f"profile {profile.profile_id} industry {profile.industry} is incompatible with {industry}"
        )
    if not profile.applies_to_size(size_band):
        raise ValueError(
            f"profile {profile.profile_id} size band {profile.size_band} ({profile.size_scope}) is incompatible with {size_band}"
        )


def compose_calibration_profiles(
    profiles: Iterable[CalibrationProfile],
    *,
    profile_id: str,
    region: RegionGroup,
    industry: IndustryFamily,
    size_band: CompanySizeBand,
) -> CalibrationProfile:
    """Fuse multiple source/domain profiles into one world-generation calibration.

    The merger is deliberately conservative. A metric is selected from the most semantically
    specific compatible profile; exact size-conditioned evidence wins over size-agnostic
    evidence at equal region/industry scope, and empirical observations beat bootstrap values.
    If two equally specific empirical profiles define the same metric, the profile with the
    larger metric-level observation count wins. Publisher row counts do not otherwise define
    cross-source weighting; that balancing happens upstream inside source materializers.
    """

    source_profiles = list(profiles)
    if not source_profiles:
        raise ValueError("at least one calibration profile is required")
    for profile in source_profiles:
        _validate_source_profile(
            profile,
            region=region,
            industry=industry,
            size_band=size_band,
        )

    selected_distributions: dict[
        str, tuple[tuple[int, int, int, int, str], QuantileDistribution]
    ] = {}
    selected_categories: dict[
        str, tuple[tuple[int, int, int, int, str], WeightedCategory]
    ] = {}

    for profile in source_profiles:
        scope, size_specificity, evidence = _profile_specificity(
            profile,
            region=region,
            industry=industry,
            size_band=size_band,
        )
        for metric, distribution in profile.distributions.items():
            rank = (
                scope,
                size_specificity,
                evidence,
                distribution.observation_count,
                profile.profile_id,
            )
            current = selected_distributions.get(metric)
            if current is None or rank > current[0]:
                selected_distributions[metric] = (rank, distribution)
        for metric, category in profile.categories.items():
            rank = (
                scope,
                size_specificity,
                evidence,
                category.observation_count,
                profile.profile_id,
            )
            current = selected_categories.get(metric)
            if current is None or rank > current[0]:
                selected_categories[metric] = (rank, category)

    distributions = {metric: value for metric, (_, value) in selected_distributions.items()}
    categories = {metric: value for metric, (_, value) in selected_categories.items()}
    source_ids = sorted({source_id for profile in source_profiles for source_id in profile.source_ids})

    empirical_counts = [
        distribution.observation_count
        for distribution in distributions.values()
        if distribution.observation_count > 0
    ] + [
        category.observation_count
        for category in categories.values()
        if category.observation_count > 0
    ]
    inherited_count = sum(
        1 for distribution in distributions.values() if distribution.observation_count == 0
    ) + sum(1 for category in categories.values() if category.observation_count == 0)

    if empirical_counts and inherited_count:
        state = "hybrid"
    elif empirical_counts:
        state = "empirical"
    else:
        state = "bootstrap_prior"

    notes = [
        "Composite calibration assembled by semantic specificity, size applicability, evidence state, and metric-level observation count.",
        "Global/generic or size-agnostic evidence is used only when no more specific compatible profile provides the same metric.",
        *(
            [f"{inherited_count} selected metrics/categories remain non-empirical priors."]
            if inherited_count
            else []
        ),
    ]
    for profile in source_profiles:
        notes.extend(f"[{profile.profile_id}] {note}" for note in profile.notes)

    return CalibrationProfile(
        profile_id=profile_id,
        version="1",
        region=region,
        industry=industry,
        size_band=size_band,
        size_scope="exact",
        source_ids=source_ids,
        distributions=distributions,
        categories=categories,
        empirical_observation_count=sum(empirical_counts),
        state=state,
        notes=notes,
    )
