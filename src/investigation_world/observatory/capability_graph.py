from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.aggregation import AggregateDriftReport
from investigation_world.observatory.models import CapabilityDriftReport, DimensionDelta


class CapabilityNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    capability_id: str
    label: str
    observed_dimension: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class CapabilityEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prerequisite: str
    dependent: str
    weight: float = Field(default=1.0, gt=0.0)


class CapabilityGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    graph_id: str = ""
    version: str = "1"
    nodes: list[CapabilityNode]
    edges: list[CapabilityEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "CapabilityGraph":
        ids = [node.capability_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("capability graph contains duplicate node ids")
        known = set(ids)
        for edge in self.edges:
            if edge.prerequisite not in known or edge.dependent not in known:
                raise ValueError("capability graph edge references an unknown node")
            if edge.prerequisite == edge.dependent:
                raise ValueError("capability graph cannot contain self edges")
        _topological_order(self.nodes, self.edges)
        payload = {
            "version": self.version,
            "nodes": [node.model_dump(mode="json") for node in self.nodes],
            "edges": [edge.model_dump(mode="json") for edge in self.edges],
        }
        expected = f"CGRAPH-{stable_hash(payload)[:20].upper()}"
        if self.graph_id and self.graph_id != expected:
            raise ValueError("graph_id does not match graph contents")
        object.__setattr__(self, "graph_id", expected)
        return self


class CapabilityAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    capability_id: str
    observed_dimension: str | None = None
    observed_delta: float | None = None
    diagnostic_score: float
    regressed_prerequisites: list[str] = Field(default_factory=list)
    explanation: str


class CapabilityAttributionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    graph_id: str
    source_kind: str
    source_id: str
    attributions: list[CapabilityAttribution] = Field(default_factory=list)
    candidate_roots: list[str] = Field(default_factory=list)
    caveat: str = (
        "Graph attribution is diagnostic, not causal proof. It identifies regressed observed "
        "dimensions and prerequisite structure that are consistent with the measured drift."
    )


def _topological_order(
    nodes: Iterable[CapabilityNode],
    edges: Iterable[CapabilityEdge],
) -> list[str]:
    ids = [node.capability_id for node in nodes]
    indegree = {item: 0 for item in ids}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        indegree[edge.dependent] += 1
        children[edge.prerequisite].append(edge.dependent)
    queue = deque(sorted(item for item, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(ordered) != len(ids):
        raise ValueError("capability graph must be acyclic")
    return ordered


def _dimension_map(report: AggregateDriftReport | CapabilityDriftReport) -> dict[str, DimensionDelta]:
    return report.dimensions


def _source_identity(report: AggregateDriftReport | CapabilityDriftReport) -> tuple[str, str]:
    if isinstance(report, AggregateDriftReport):
        return "aggregate", report.current_aggregate_id
    return "run", report.current_run_id


def attribute_drift(
    graph: CapabilityGraph,
    report: AggregateDriftReport | CapabilityDriftReport,
    *,
    tolerance: float = 1e-9,
) -> CapabilityAttributionReport:
    dimensions = _dimension_map(report)
    nodes = {node.capability_id: node for node in graph.nodes}
    parents: dict[str, list[CapabilityEdge]] = defaultdict(list)
    children: dict[str, list[CapabilityEdge]] = defaultdict(list)
    for edge in graph.edges:
        parents[edge.dependent].append(edge)
        children[edge.prerequisite].append(edge)

    direct: dict[str, float] = {}
    for node in graph.nodes:
        delta = dimensions.get(node.observed_dimension or "")
        direct[node.capability_id] = max(0.0, -(delta.delta if delta is not None else 0.0))

    propagated = dict(direct)
    order = _topological_order(graph.nodes, graph.edges)
    for node_id in order:
        if propagated[node_id] <= tolerance:
            continue
        for edge in children[node_id]:
            propagated[edge.dependent] += propagated[node_id] * edge.weight

    attributions: list[CapabilityAttribution] = []
    regressed_ids = {item for item, score in direct.items() if score > tolerance}
    for node_id in order:
        node = nodes[node_id]
        observed = dimensions.get(node.observed_dimension or "")
        regressed_prereqs = sorted(
            edge.prerequisite
            for edge in parents[node_id]
            if edge.prerequisite in regressed_ids
        )
        score = propagated[node_id]
        if score <= tolerance and observed is None:
            continue
        explanation_parts: list[str] = []
        if observed is not None:
            direction = "regressed" if observed.delta < -tolerance else "improved" if observed.delta > tolerance else "was stable"
            explanation_parts.append(
                f"Observed dimension {node.observed_dimension!r} {direction} by {observed.delta:.6g}."
            )
        if regressed_prereqs:
            explanation_parts.append(
                "Regressed declared prerequisites: " + ", ".join(regressed_prereqs) + "."
            )
        if not explanation_parts:
            explanation_parts.append("No directly observed dimension is mapped to this capability.")
        attributions.append(
            CapabilityAttribution(
                capability_id=node_id,
                observed_dimension=node.observed_dimension,
                observed_delta=observed.delta if observed is not None else None,
                diagnostic_score=score,
                regressed_prerequisites=regressed_prereqs,
                explanation=" ".join(explanation_parts),
            )
        )

    candidate_roots = sorted(
        node_id
        for node_id in regressed_ids
        if not any(edge.prerequisite in regressed_ids for edge in parents[node_id])
    )
    source_kind, source_id = _source_identity(report)
    return CapabilityAttributionReport(
        graph_id=graph.graph_id,
        source_kind=source_kind,
        source_id=source_id,
        attributions=sorted(attributions, key=lambda item: (-item.diagnostic_score, item.capability_id)),
        candidate_roots=candidate_roots,
    )


def companyworld_investigation_capability_graph() -> CapabilityGraph:
    return CapabilityGraph(
        version="companyworld-investigation-v1",
        nodes=[
            CapabilityNode(capability_id="evidence_selection", label="Evidence selection", observed_dimension="evidence_support"),
            CapabilityNode(capability_id="fact_precision", label="Fact precision", observed_dimension="fact_precision"),
            CapabilityNode(capability_id="fact_recall", label="Fact recall", observed_dimension="fact_recall"),
            CapabilityNode(capability_id="fact_resolution", label="Fact resolution", observed_dimension="fact_score"),
            CapabilityNode(capability_id="calibration", label="Confidence calibration", observed_dimension="calibration"),
            CapabilityNode(capability_id="abstention", label="Appropriate abstention", observed_dimension="abstention"),
            CapabilityNode(capability_id="efficiency", label="Investigation efficiency", observed_dimension="efficiency"),
        ],
        edges=[
            CapabilityEdge(prerequisite="evidence_selection", dependent="fact_precision", weight=0.5),
            CapabilityEdge(prerequisite="evidence_selection", dependent="fact_recall", weight=0.5),
            CapabilityEdge(prerequisite="fact_precision", dependent="fact_resolution", weight=0.5),
            CapabilityEdge(prerequisite="fact_recall", dependent="fact_resolution", weight=0.5),
            CapabilityEdge(prerequisite="fact_resolution", dependent="calibration", weight=0.25),
        ],
    )
