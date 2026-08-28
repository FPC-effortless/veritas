from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.foundry.world_calibration import (
    CalibrationSource,
    CalibrationSourceKind,
    DependencyTarget,
    DistributionTarget,
    ProcedurePrior,
    WorldCalibrationSpec,
)


class DatasetFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    PARQUET = "parquet"


class CalibrationStatistic(StrEnum):
    COUNT_ROWS = "count_rows"
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    DISTINCT_COUNT = "distinct_count"
    NULL_RATE = "null_rate"
    QUANTILE = "quantile"
    CATEGORY_DISTRIBUTION = "category_distribution"


class CalibrationDataset(BaseModel):
    source_id: str
    path: Path
    name: str
    kind: CalibrationSourceKind = CalibrationSourceKind.PUBLIC_DATASET
    version: str = "unspecified"
    population: str | None = None
    format: DatasetFormat | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality_notes: list[str] = Field(default_factory=list)


class DistributionFitRule(BaseModel):
    target_id: str
    source_id: str
    object_type: str
    attribute: str
    statistic: CalibrationStatistic
    column: str | None = None
    tolerance: float | None = Field(default=None, ge=0.0)
    conditioning: dict[str, Any] = Field(default_factory=dict)
    quantile: float | None = Field(default=None, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def validate_rule(self):
        if self.statistic != CalibrationStatistic.COUNT_ROWS and self.column is None:
            raise ValueError(f"{self.statistic.value} requires column")
        if self.statistic == CalibrationStatistic.QUANTILE and self.quantile is None:
            raise ValueError("quantile statistic requires quantile")
        return self


class DependencyFitRule(BaseModel):
    target_id: str
    source_id: str
    cause: str
    effect: str
    cause_column: str
    effect_column: str
    relationship: str = "pearson_correlation"
    lag: str | None = None


class CalibrationIngestionPlan(BaseModel):
    calibration_id: str
    version: str = "1"
    domain: str
    datasets: list[CalibrationDataset]
    distribution_rules: list[DistributionFitRule] = Field(default_factory=list)
    dependency_rules: list[DependencyFitRule] = Field(default_factory=list)
    procedure_priors: list[ProcedurePrior] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sources(self):
        source_ids = [dataset.source_id for dataset in self.datasets]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("calibration dataset source_id values must be unique")
        known = set(source_ids)
        for rule in [*self.distribution_rules, *self.dependency_rules]:
            if rule.source_id not in known:
                raise ValueError(
                    f"calibration rule {rule.target_id} references unknown source {rule.source_id}"
                )
        return self


class DatasetProfile(BaseModel):
    source_id: str
    format: DatasetFormat
    file_sha256: str
    row_count: int = Field(ge=0)
    columns: dict[str, str] = Field(default_factory=dict)
    null_fraction: dict[str, float] = Field(default_factory=dict)
    distinct_count: dict[str, int] = Field(default_factory=dict)
    numeric_summary: dict[str, dict[str, float | None]] = Field(default_factory=dict)


class CalibrationIngestionResult(BaseModel):
    spec: WorldCalibrationSpec
    profiles: dict[str, DatasetProfile]
    warnings: list[str] = Field(default_factory=list)
    plan_hash: str


_NUMERIC_MARKERS = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "DECIMAL",
    "FLOAT",
    "DOUBLE",
    "REAL",
)


def _dataset_format(dataset: CalibrationDataset) -> DatasetFormat:
    if dataset.format is not None:
        return dataset.format
    suffix = dataset.path.suffix.casefold()
    mapping = {
        ".csv": DatasetFormat.CSV,
        ".json": DatasetFormat.JSON,
        ".jsonl": DatasetFormat.JSONL,
        ".ndjson": DatasetFormat.JSONL,
        ".parquet": DatasetFormat.PARQUET,
    }
    try:
        return mapping[suffix]
    except KeyError as error:
        raise ValueError(
            f"cannot infer dataset format for {dataset.path}; set format explicitly"
        ) from error


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _reader_sql(dataset: CalibrationDataset) -> str:
    path = _sql_string(str(dataset.path))
    dataset_format = _dataset_format(dataset)
    if dataset_format == DatasetFormat.CSV:
        return f"read_csv_auto({path}, header=true, sample_size=-1)"
    if dataset_format in {DatasetFormat.JSON, DatasetFormat.JSONL}:
        return f"read_json_auto({path}, format='auto')"
    if dataset_format == DatasetFormat.PARQUET:
        return f"read_parquet({path})"
    raise ValueError(f"unsupported dataset format: {dataset_format}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _where_clause(
    conditioning: dict[str, Any],
    *,
    known_columns: set[str],
) -> tuple[str, list[Any]]:
    if not conditioning:
        return "", []
    fragments: list[str] = []
    values: list[Any] = []
    for column, value in sorted(conditioning.items()):
        if column not in known_columns:
            raise ValueError(f"conditioning references unknown column {column}")
        identifier = _quote_identifier(column)
        if value is None:
            fragments.append(f"{identifier} IS NULL")
        else:
            fragments.append(f"{identifier} = ?")
            values.append(value)
    return " WHERE " + " AND ".join(fragments), values


def profile_dataset(
    dataset: CalibrationDataset,
    *,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> DatasetProfile:
    if not dataset.path.exists() or not dataset.path.is_file():
        raise FileNotFoundError(dataset.path)
    owned = connection is None
    conn = connection or duckdb.connect(database=":memory:")
    try:
        reader = _reader_sql(dataset)
        description = conn.execute(f"DESCRIBE SELECT * FROM {reader}").fetchall()
        columns = {str(row[0]): str(row[1]) for row in description}
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {reader}").fetchone()[0])
        null_fraction: dict[str, float] = {}
        distinct_count: dict[str, int] = {}
        numeric_summary: dict[str, dict[str, float | None]] = {}

        for column, column_type in columns.items():
            identifier = _quote_identifier(column)
            nulls, distinct = conn.execute(
                f"SELECT COUNT(*) - COUNT({identifier}), "
                f"COUNT(DISTINCT {identifier}) FROM {reader}"
            ).fetchone()
            null_fraction[column] = float(nulls) / max(1, row_count)
            distinct_count[column] = int(distinct)
            if any(marker in column_type.upper() for marker in _NUMERIC_MARKERS):
                values = conn.execute(
                    "SELECT "
                    f"MIN({identifier}), MAX({identifier}), AVG({identifier}), "
                    f"MEDIAN({identifier}), STDDEV_POP({identifier}), "
                    f"QUANTILE_CONT({identifier}, 0.25), "
                    f"QUANTILE_CONT({identifier}, 0.75) "
                    f"FROM {reader}"
                ).fetchone()
                keys = ["min", "max", "mean", "median", "stddev", "q25", "q75"]
                numeric_summary[column] = {
                    key: None if value is None else float(value)
                    for key, value in zip(keys, values, strict=True)
                }

        return DatasetProfile(
            source_id=dataset.source_id,
            format=_dataset_format(dataset),
            file_sha256=_file_sha256(dataset.path),
            row_count=row_count,
            columns=columns,
            null_fraction=null_fraction,
            distinct_count=distinct_count,
            numeric_summary=numeric_summary,
        )
    finally:
        if owned:
            conn.close()


def _fit_distribution_target(
    dataset: CalibrationDataset,
    profile: DatasetProfile,
    rule: DistributionFitRule,
    conn: duckdb.DuckDBPyConnection,
) -> DistributionTarget:
    reader = _reader_sql(dataset)
    known_columns = set(profile.columns)
    where, params = _where_clause(rule.conditioning, known_columns=known_columns)

    if rule.statistic == CalibrationStatistic.COUNT_ROWS:
        expected: Any = int(
            conn.execute(f"SELECT COUNT(*) FROM {reader}{where}", params).fetchone()[0]
        )
    else:
        assert rule.column is not None
        if rule.column not in known_columns:
            raise ValueError(
                f"distribution rule {rule.target_id} references unknown column {rule.column}"
            )
        identifier = _quote_identifier(rule.column)
        if rule.statistic == CalibrationStatistic.NULL_RATE:
            nulls, total = conn.execute(
                f"SELECT COUNT(*) - COUNT({identifier}), COUNT(*) "
                f"FROM {reader}{where}",
                params,
            ).fetchone()
            expected = float(nulls) / max(1, int(total))
        elif rule.statistic == CalibrationStatistic.DISTINCT_COUNT:
            expected = int(
                conn.execute(
                    f"SELECT COUNT(DISTINCT {identifier}) FROM {reader}{where}",
                    params,
                ).fetchone()[0]
            )
        elif rule.statistic == CalibrationStatistic.CATEGORY_DISTRIBUTION:
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM {reader}{where}", params).fetchone()[0]
            )
            rows = conn.execute(
                f"SELECT CAST({identifier} AS VARCHAR), COUNT(*) AS n "
                f"FROM {reader}{where} "
                "GROUP BY 1 ORDER BY n DESC, 1 ASC LIMIT 50",
                params,
            ).fetchall()
            expected = {
                "<NULL>" if value is None else str(value): float(count) / max(1, total)
                for value, count in rows
            }
        else:
            aggregate = {
                CalibrationStatistic.MEAN: "AVG",
                CalibrationStatistic.MEDIAN: "MEDIAN",
                CalibrationStatistic.MIN: "MIN",
                CalibrationStatistic.MAX: "MAX",
            }.get(rule.statistic)
            if rule.statistic == CalibrationStatistic.QUANTILE:
                assert rule.quantile is not None
                query = (
                    f"SELECT QUANTILE_CONT({identifier}, {float(rule.quantile)}) "
                    f"FROM {reader}{where}"
                )
            elif aggregate is not None:
                query = f"SELECT {aggregate}({identifier}) FROM {reader}{where}"
            else:
                raise ValueError(f"unsupported statistic {rule.statistic}")
            value = conn.execute(query, params).fetchone()[0]
            if value is None:
                raise ValueError(f"distribution rule {rule.target_id} produced no value")
            expected = float(value) if isinstance(value, (int, float)) else str(value)

    return DistributionTarget(
        target_id=rule.target_id,
        object_type=rule.object_type,
        attribute=rule.attribute,
        statistic=rule.statistic.value,
        expected_value=expected,
        tolerance=rule.tolerance,
        conditioning=rule.conditioning,
        source_ids=[rule.source_id],
    )


def _fit_dependency_target(
    dataset: CalibrationDataset,
    profile: DatasetProfile,
    rule: DependencyFitRule,
    conn: duckdb.DuckDBPyConnection,
) -> DependencyTarget:
    known = set(profile.columns)
    missing = {rule.cause_column, rule.effect_column} - known
    if missing:
        raise ValueError(
            f"dependency rule {rule.target_id} references unknown columns {sorted(missing)}"
        )
    if rule.relationship != "pearson_correlation":
        raise ValueError(
            f"unsupported dependency relationship {rule.relationship}; "
            "currently supported: pearson_correlation"
        )
    cause = _quote_identifier(rule.cause_column)
    effect = _quote_identifier(rule.effect_column)
    value = conn.execute(
        f"SELECT CORR({cause}, {effect}) FROM {_reader_sql(dataset)} "
        f"WHERE {cause} IS NOT NULL AND {effect} IS NOT NULL"
    ).fetchone()[0]
    return DependencyTarget(
        target_id=rule.target_id,
        cause=rule.cause,
        effect=rule.effect,
        relationship=rule.relationship,
        strength=None if value is None else float(value),
        lag=rule.lag,
        source_ids=[rule.source_id],
    )


def fit_calibration_plan(plan: CalibrationIngestionPlan) -> CalibrationIngestionResult:
    datasets = {dataset.source_id: dataset for dataset in plan.datasets}
    profiles: dict[str, DatasetProfile] = {}
    sources: list[CalibrationSource] = []
    warnings: list[str] = []

    conn = duckdb.connect(database=":memory:")
    try:
        for dataset in plan.datasets:
            profile = profile_dataset(dataset, connection=conn)
            profiles[dataset.source_id] = profile
            if profile.row_count == 0:
                warnings.append(f"{dataset.source_id}: dataset is empty")
            provenance = {
                **dataset.provenance,
                "filename": dataset.path.name,
                "format": profile.format.value,
                "sha256": profile.file_sha256,
                "row_count": profile.row_count,
            }
            sources.append(
                CalibrationSource(
                    source_id=dataset.source_id,
                    kind=dataset.kind,
                    name=dataset.name,
                    version=dataset.version,
                    schema_ref=f"duckdb:{profile.format.value}",
                    population=dataset.population,
                    fields=list(profile.columns),
                    provenance=provenance,
                    quality_notes=dataset.quality_notes,
                )
            )

        distribution_targets = [
            _fit_distribution_target(
                datasets[rule.source_id],
                profiles[rule.source_id],
                rule,
                conn,
            )
            for rule in plan.distribution_rules
        ]
        dependency_targets = [
            _fit_dependency_target(
                datasets[rule.source_id],
                profiles[rule.source_id],
                rule,
                conn,
            )
            for rule in plan.dependency_rules
        ]
        for target in dependency_targets:
            if target.strength is None:
                warnings.append(f"{target.target_id}: dependency strength is undefined")
    finally:
        conn.close()

    spec = WorldCalibrationSpec(
        calibration_id=plan.calibration_id,
        version=plan.version,
        domain=plan.domain,
        sources=sources,
        distribution_targets=distribution_targets,
        dependency_targets=dependency_targets,
        procedure_priors=plan.procedure_priors,
        exclusions=plan.exclusions,
        notes=plan.notes,
    )
    return CalibrationIngestionResult(
        spec=spec,
        profiles=profiles,
        warnings=warnings,
        plan_hash=stable_hash(plan.model_dump(mode="json")),
    )
