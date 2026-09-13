"""Phase-1 CASM Boolean benchmark generator.

The generator is intentionally independent of PyTorch. It establishes the
structural benchmark and exact Boolean oracle before a learned router exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import itertools
import random


class Op(str, Enum):
    INPUT = "INPUT"
    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    NOT = "NOT"
    OUTPUT = "OUTPUT"


COMMUTATIVE = frozenset({Op.AND, Op.OR, Op.XOR})
ARITY = {Op.INPUT: 0, Op.AND: 2, Op.OR: 2, Op.XOR: 2, Op.NOT: 1, Op.OUTPUT: 1}


@dataclass(frozen=True)
class Node:
    slot: int
    op: Op
    depth: int
    role: str


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    relation: str


@dataclass(frozen=True)
class BooleanProgram:
    """One episode embedded in a fixed slot universe and fixed DAG superset."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    inputs: tuple[int, ...]
    output: int
    existence: tuple[int, ...]
    n_inputs: int

    @property
    def num_slots(self) -> int:
        return len(self.existence)

    @property
    def true_edge_set(self) -> frozenset[tuple[int, int]]:
        return frozenset((e.src, e.dst) for e in self.edges)

    @property
    def active_nodes(self) -> tuple[int, ...]:
        return tuple(i for i, present in enumerate(self.existence) if present)

    @property
    def admissible_edge_set(self) -> frozenset[tuple[int, int]]:
        """Fixed structural superset A restricted only by episode existence."""
        active = self.active_nodes
        return frozenset((src, dst) for src in active for dst in active if src < dst)

    @property
    def distractor_edge_set(self) -> frozenset[tuple[int, int]]:
        return self.admissible_edge_set - self.true_edge_set

    def canonical_key(self) -> tuple:
        """Deduplication key; raw operand order is not rewritten."""
        node_key = tuple((n.slot, n.op.value, n.depth, n.role) for n in self.nodes if self.existence[n.slot])
        edge_key = tuple(sorted((e.src, e.dst, e.relation) for e in self.edges))
        return node_key, edge_key, self.inputs, self.output

    def evaluate(self, bits: tuple[int, ...]) -> int:
        if len(bits) != self.n_inputs or any(b not in (0, 1) for b in bits):
            raise ValueError("bits must contain exactly n_inputs binary values")
        nodes = {node.slot: node for node in self.nodes}
        values: dict[int, int] = {slot: int(bits[k]) for k, slot in enumerate(self.inputs)}
        incoming: dict[int, list[Edge]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.dst, []).append(edge)
        for slot in sorted(self.active_nodes):
            node = nodes[slot]
            if node.op is Op.INPUT:
                continue
            args = sorted(incoming.get(slot, []), key=lambda e: e.relation)
            xs = [values[e.src] for e in args]
            if node.op is Op.AND:
                values[slot] = xs[0] & xs[1]
            elif node.op is Op.OR:
                values[slot] = xs[0] | xs[1]
            elif node.op is Op.XOR:
                values[slot] = xs[0] ^ xs[1]
            elif node.op is Op.NOT:
                values[slot] = 1 - xs[0]
            elif node.op is Op.OUTPUT:
                values[slot] = xs[0]
            else:
                raise AssertionError(f"unsupported op: {node.op}")
        return values[self.output]

    def truth_table(self) -> tuple[int, ...]:
        return tuple(self.evaluate(bits) for bits in itertools.product((0, 1), repeat=self.n_inputs))


class BooleanDAGGenerator:
    """Generate typed Boolean programs inside a fixed lower-triangular superset.

    Slots are topological positions. The fixed admissible substrate is
    ``A[src,dst] = 1 iff src < dst``. An episode's true graph is a strict
    subset of A, so existence plus A does not reveal the true wiring.
    """

    SYNTACTIC_RELATIONS = ("arg1", "arg2")

    def __init__(self, num_slots: int = 16, max_depth: int = 8, n_inputs: int = 4, seed: int = 42):
        if num_slots < n_inputs + 2:
            raise ValueError("num_slots is too small for the requested structure")
        if not 1 <= max_depth <= 8:
            raise ValueError("max_depth must be in [1, 8]")
        if not 1 <= n_inputs <= min(8, num_slots - 1):
            raise ValueError("n_inputs must be in [1, min(8, num_slots-1)]")
        self.num_slots = num_slots
        self.max_depth = max_depth
        self.n_inputs = n_inputs
        self.rng = random.Random(seed)

    def generate(self, depth: int | None = None, width: int | None = None) -> BooleanProgram:
        max_program_depth = depth if depth is not None else self.rng.randint(1, self.max_depth)
        width = width if width is not None else self.rng.randint(self.n_inputs + 1, min(self.num_slots, 8))
        if not 1 <= max_program_depth <= self.max_depth:
            raise ValueError("invalid depth")
        if width < self.n_inputs + 1 or width > self.num_slots:
            raise ValueError("invalid width")

        active = tuple(range(width))
        input_slots = tuple(range(self.n_inputs))
        output_slot = width - 1
        internal = tuple(range(self.n_inputs, output_slot))

        # Assign each internal node to a layer first. Edges are then sampled only
        # from earlier layers, guaranteeing both acyclicity and depth <= requested.
        layers: dict[int, int] = {slot: 0 for slot in input_slots}
        for slot in internal:
            layers[slot] = self.rng.randint(1, max_program_depth)

        ops: dict[int, Op] = {slot: Op.INPUT for slot in input_slots}
        for slot in internal:
            ops[slot] = self.rng.choice((Op.AND, Op.OR, Op.XOR, Op.NOT))
        ops[output_slot] = Op.OUTPUT
        layers[output_slot] = max_program_depth + 1

        edges: list[Edge] = []
        for slot in (*internal, output_slot):
            candidates = [src for src in active if src < slot and layers[src] < layers[slot]]
            op = ops[slot]
            if op in (Op.NOT, Op.OUTPUT):
                edges.append(Edge(self.rng.choice(candidates), slot, "arg1"))
            else:
                if len(candidates) < 2:
                    # A binary node on a new layer must have two earlier sources.
                    # With at least two input slots this can always be repaired by
                    # assigning it to layer 1.
                    layers[slot] = 1
                    candidates = [src for src in active if src < slot and layers[src] < 1]
                src1, src2 = self.rng.sample(candidates, 2)
                edges.extend((Edge(src1, slot, "arg1"), Edge(src2, slot, "arg2")))

        # Recompute actual longest-path depths from the sampled edges. This is the
        # diagnostic depth, rather than trusting the requested layer assignment.
        incoming: dict[int, list[int]] = {}
        for edge in edges:
            incoming.setdefault(edge.dst, []).append(edge.src)
        actual_depth = {slot: 0 for slot in input_slots}
        for slot in (*internal, output_slot):
            actual_depth[slot] = 1 + max(actual_depth[src] for src in incoming[slot])
        if actual_depth[output_slot] > max_program_depth + 1:
            raise AssertionError("internal generator error: sampled depth exceeded bound")

        nodes = tuple(
            Node(slot, ops[slot], actual_depth[slot], "output" if slot == output_slot else f"op_{slot}")
            for slot in active
        )
        existence = tuple(1 if i in active else 0 for i in range(self.num_slots))
        program = BooleanProgram(nodes, tuple(edges), input_slots, output_slot, existence, self.n_inputs)
        validate_program(program)
        return program


@lru_cache(maxsize=None)
def exhaustive_table(program: BooleanProgram) -> tuple[int, ...]:
    return program.truth_table()


def validate_program(program: BooleanProgram) -> None:
    """Raise AssertionError if any Phase-1 structural invariant is violated."""
    assert len(program.existence) == program.num_slots
    active = set(program.active_nodes)
    nodes = {node.slot: node for node in program.nodes}
    assert set(nodes) == active
    assert program.output in active
    assert all(slot in active for slot in program.inputs)
    assert len(set(program.inputs)) == len(program.inputs) == program.n_inputs
    assert all(nodes[slot].op is Op.INPUT for slot in program.inputs)
    assert nodes[program.output].op is Op.OUTPUT

    edge_pairs = {(e.src, e.dst) for e in program.edges}
    assert len(edge_pairs) == len(program.edges)
    assert all(e.src in active and e.dst in active for e in program.edges)
    assert all(e.src < e.dst for e in program.edges), "true edges must respect fixed A"
    assert all((e.src, e.dst) in program.admissible_edge_set for e in program.edges)
    assert all(e.relation in ("arg1", "arg2") for e in program.edges)

    incoming: dict[int, list[Edge]] = {}
    for e in program.edges:
        incoming.setdefault(e.dst, []).append(e)
    for node in program.nodes:
        if not program.existence[node.slot] or node.op is Op.INPUT:
            continue
        ins = incoming.get(node.slot, [])
        assert len(ins) == ARITY[node.op]
        if node.op in COMMUTATIVE:
            assert {e.relation for e in ins} == {"arg1", "arg2"}
        else:
            assert {e.relation for e in ins} == {"arg1"}
        assert all(nodes[e.src].depth < node.depth for e in ins)

    # Independent Kahn check; depth labels are not trusted as the acyclicity proof.
    indegree = {slot: 0 for slot in active}
    successors: dict[int, list[int]] = {slot: [] for slot in active}
    for e in program.edges:
        indegree[e.dst] += 1
        successors[e.src].append(e.dst)
    queue = [slot for slot in active if indegree[slot] == 0]
    seen = 0
    while queue:
        slot = queue.pop()
        seen += 1
        for dst in successors[slot]:
            indegree[dst] -= 1
            if indegree[dst] == 0:
                queue.append(dst)
    assert seen == len(active), "program contains a cycle"


def relabel_operands(program: BooleanProgram) -> BooleanProgram:
    """Return the raw arg1<->arg2 relabeling used by permutation diagnostics."""
    edges = tuple(
        Edge(e.src, e.dst, "arg2" if e.relation == "arg1" else "arg1") for e in program.edges
    )
    return BooleanProgram(program.nodes, edges, program.inputs, program.output, program.existence, program.n_inputs)
