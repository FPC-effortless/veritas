from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from .models import TaskDiversityReport, entropy_metrics, stable_content_hash

_TOKEN_RE = re.compile(r"[a-zA-Z_]+|\d+(?:\.\d+)?")
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.I)
_HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_TRAILING_ID_RE = re.compile(r"\b([a-z_\-]+)\d+\b", re.I)


class SemanticClusterBackend(Protocol):
    name: str

    def cluster_keys(self, records: Sequence[dict[str, Any]]) -> list[str]: ...


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(k) for k in sorted(value)]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, "", [], {}):
            return record[key]
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for key in keys:
            if key in metadata and metadata[key] not in (None, "", [], {}):
                return metadata[key]
    return None


def normalized_text(record: dict[str, Any]) -> str:
    candidates = [
        _first(record, "normalized_text"),
        _first(record, "text", "prompt", "description", "title", "instruction"),
    ]
    text = " ".join(str(v) for v in candidates if v)
    text = text.lower()
    text = _UUID_RE.sub(" <id> ", text)
    text = _HEX_RE.sub(" <hex> ", text)
    text = _NUMBER_RE.sub(" <num> ", text)
    text = _TRAILING_ID_RE.sub(r"\1<id>", text)
    return " ".join(_TOKEN_RE.findall(text))


def _sequence_signature(record: dict[str, Any]) -> str | None:
    value = _first(record, "action_sequence", "tool_sequence", "actions", "tools", "steps")
    items = _as_list(value)
    return ">".join(items) if items else None


def _topology_signature(record: dict[str, Any]) -> str | None:
    explicit = _first(record, "workflow_topology", "topology", "graph_signature")
    if explicit:
        return str(explicit)
    steps = _as_list(_first(record, "workflow_steps", "steps", "actions"))
    deps = _first(record, "dependencies", "edges")
    if steps or deps:
        dep_count = len(deps) if isinstance(deps, (list, tuple, set, dict)) else int(bool(deps))
        return f"steps={len(steps)}|deps={dep_count}|seq={_sequence_signature(record) or ''}"
    return None


def _component_signature(record: dict[str, Any]) -> str | None:
    components = _as_list(
        _first(record, "components", "component_ids", "capability_tags", "systems", "subtasks")
    )
    return "+".join(sorted(set(components))) if components else None


def _artifact_schema_signature(record: dict[str, Any]) -> str | None:
    value = _first(record, "artifact_schema", "artifact_type", "schema", "output_schema")
    if isinstance(value, dict):
        return stable_content_hash(value)[:16]
    items = _as_list(value)
    return "+".join(sorted(set(items))) if items else None


def _simhash64(features: list[str]) -> int:
    if not features:
        return 0
    vector = [0] * 64
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()[:8]
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


class LexicalStructuralSimHashBackend:
    """Offline deterministic proxy; replaceable by an embedding backend later."""

    name = "lexical-structural-simhash-v1"

    def __init__(self, prefix_bits: int = 14) -> None:
        self.prefix_bits = prefix_bits

    def cluster_keys(self, records: Sequence[dict[str, Any]]) -> list[str]:
        keys: list[str] = []
        for record in records:
            text = normalized_text(record)
            tokens = text.split()
            features = tokens + [
                "_".join(tokens[i : i + 2])
                for i in range(max(0, len(tokens) - 1))
            ]
            structural = [
                _topology_signature(record) or "",
                _sequence_signature(record) or "",
                _component_signature(record) or "",
                str(_first(record, "grammar_family", "grammar_id", "generator_family") or ""),
            ]
            features.extend(f"struct:{item}" for item in structural if item)
            simhash = _simhash64(features)
            prefix = simhash >> (64 - self.prefix_bits)
            coarse_structure = stable_content_hash(structural)[:8]
            keys.append(f"{coarse_structure}:{prefix:04x}")
        return keys


def _near_duplicate_key(record: dict[str, Any]) -> str:
    payload = {
        "text": normalized_text(record),
        "topology": _topology_signature(record),
        "sequence": _sequence_signature(record),
        "components": _component_signature(record),
        "grammar": _first(record, "grammar_family", "grammar_id", "generator_family"),
        "verifier": _as_list(
            _first(record, "verifier_conditions", "verification_conditions", "checks")
        ),
        "artifact": _artifact_schema_signature(record),
    }
    return stable_content_hash(payload)


def _exact_content_key(record: dict[str, Any]) -> str:
    payload = {
        "text": normalized_text(record),
        "topology": _topology_signature(record),
        "sequence": _sequence_signature(record),
        "components": _component_signature(record),
        "failure": _as_list(_first(record, "failure_mode", "failure_modes", "causal_class")),
        "verifier": _as_list(
            _first(record, "verifier_conditions", "verification_conditions", "checks")
        ),
        "artifact": _artifact_schema_signature(record),
    }
    return stable_content_hash(payload)


def _category(records: Sequence[dict[str, Any]], getter) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        value = getter(record)
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            key = "+".join(sorted(set(str(v) for v in value)))
        else:
            key = str(value)
        counts[key] += 1
    return counts


def _harmonic_mean(values: list[float]) -> float:
    positive = [v for v in values if v > 0]
    if not positive:
        return 0.0
    return len(positive) / sum(1.0 / value for value in positive)


def compute_task_diversity(
    tasks: Sequence[dict[str, Any]],
    *,
    benchmark_name: str | None = None,
    benchmark_version: str | None = None,
    candidate_id: str | None = None,
    panel_id: str | None = None,
    qualification_report_id: str | None = None,
    evidence_manifest_id: str | None = None,
    release_manifest_id: str | None = None,
    input_artifact_hashes: dict[str, str] | None = None,
    cluster_backend: SemanticClusterBackend | None = None,
) -> TaskDiversityReport:
    records = [dict(item) for item in tasks]
    n = len(records)
    backend = cluster_backend or LexicalStructuralSimHashBackend()

    dimension_counts: dict[str, Counter[str]] = {
        "source_family": _category(
            records,
            lambda r: _first(r, "source_family", "source_group_id", "provider", "source"),
        ),
        "workflow_topology": _category(records, _topology_signature),
        "tool_action_sequence": _category(records, _sequence_signature),
        "causal_failure_mode": _category(
            records, lambda r: _first(r, "failure_mode", "failure_modes", "causal_class")
        ),
        "verifier_condition": _category(
            records,
            lambda r: _as_list(
                _first(r, "verifier_conditions", "verification_conditions", "checks")
            ),
        ),
        "artifact_schema": _category(records, _artifact_schema_signature),
        "component_signature": _category(records, _component_signature),
        "grammar_family": _category(
            records, lambda r: _first(r, "grammar_family", "grammar_id", "generator_family")
        ),
    }

    cluster_keys = backend.cluster_keys(records) if records else []
    cluster_counts = Counter(cluster_keys)
    dimension_counts["semantic_cluster_proxy"] = cluster_counts
    dimensions = {name: entropy_metrics(dict(counts)) for name, counts in dimension_counts.items()}

    available_effective = [
        metric.effective_number for metric in dimensions.values() if metric.available
    ]
    effective_diversity = min(float(n), _harmonic_mean(available_effective)) if n else 0.0

    exact_counts = Counter(_exact_content_key(record) for record in records)
    near_counts = Counter(_near_duplicate_key(record) for record in records)
    duplicate_excess = sum(count - 1 for count in exact_counts.values() if count > 1)
    near_excess = sum(count - 1 for count in near_counts.values() if count > 1)
    near_components = sorted((count for count in near_counts.values() if count > 1), reverse=True)

    splits: dict[str, set[str]] = defaultdict(set)
    component_splits: dict[str, set[str]] = defaultdict(set)
    primitive_components: dict[str, set[str]] = defaultdict(set)
    grammar_splits: dict[str, set[str]] = defaultdict(set)
    for record, near_key in zip(records, (_near_duplicate_key(r) for r in records), strict=True):
        split = str(_first(record, "split", "dataset_split", "partition") or "unspecified")
        splits[split].add(near_key)
        component_sig = _component_signature(record)
        if component_sig:
            component_splits[split].add(component_sig)
            primitive_components[split].update(component_sig.split("+"))
        grammar = _first(record, "grammar_family", "grammar_id", "generator_family")
        if grammar:
            grammar_splits[split].add(str(grammar))

    overlap_pairs: dict[str, int] = {}
    split_names = sorted(splits)
    for i, left in enumerate(split_names):
        for right in split_names[i + 1 :]:
            overlap_pairs[f"{left}|{right}"] = len(splits[left] & splits[right])

    train_name = "train" if "train" in splits else (split_names[0] if split_names else None)
    non_train = [name for name in split_names if name != train_name]
    component_combo_overlap = 0
    primitive_component_overlap = 0
    grammar_overlap = 0
    if train_name is not None:
        for split in non_train:
            component_combo_overlap += len(component_splits[train_name] & component_splits[split])
            primitive_component_overlap += len(
                primitive_components[train_name] & primitive_components[split]
            )
            grammar_overlap += len(grammar_splits[train_name] & grammar_splits[split])

    source_metric = dimensions["source_family"]
    largest_cluster_share = max(cluster_counts.values(), default=0) / n if n else 0.0
    return TaskDiversityReport(
        benchmark_name=benchmark_name,
        benchmark_version=benchmark_version,
        candidate_id=candidate_id,
        panel_id=panel_id,
        qualification_report_id=qualification_report_id,
        evidence_manifest_id=evidence_manifest_id,
        release_manifest_id=release_manifest_id,
        input_artifact_hashes=input_artifact_hashes or {},
        raw_task_count=n,
        effective_diversity=round(effective_diversity, 8),
        effective_diversity_method=(
            "harmonic mean of available categorical effective-number metrics"
        ),
        cluster_count=len(cluster_counts),
        largest_cluster_share=round(largest_cluster_share, 8),
        source_concentration=(
            source_metric.largest_category_share if source_metric.available else 0.0
        ),
        duplicate_share=round(duplicate_excess / n, 8) if n else 0.0,
        near_duplicate_share=round(near_excess / n, 8) if n else 0.0,
        near_duplicate_component_sizes=near_components,
        dimensions=dimensions,
        split_overlap={
            "near_duplicate_cluster_overlap_counts": overlap_pairs,
            "cross_split_near_duplicate_overlap": any(v > 0 for v in overlap_pairs.values()),
        },
        compositional_disjointness={
            "train_split": train_name,
            "non_train_splits": non_train,
            "component_combination_overlap_count": component_combo_overlap,
            "primitive_component_overlap_count": primitive_component_overlap,
            "grammar_overlap_count": grammar_overlap,
            "component_disjoint": bool(non_train) and primitive_component_overlap == 0,
            "compositional_disjoint": bool(non_train) and component_combo_overlap == 0,
            "grammar_disjoint": bool(non_train) and grammar_overlap == 0,
        },
        semantic_cluster_backend=backend.name,
    )
