"""Exhaustive Phase-1 generator tests.

These tests are deliberately independent of CASM/PyTorch. They establish that
the benchmark itself has the structural properties required for a routing test.
"""
from __future__ import annotations

import itertools

import pytest

from investigation_world.casm_phase1.boolean_dag import (
    ARITY,
    BooleanDAGGenerator,
    BooleanProgram,
    Edge,
    Node,
    Op,
    relabel_operands,
    validate_program,
)


def test_generated_programs_validate_across_depths_and_widths() -> None:
    for seed in range(12):
        generator = BooleanDAGGenerator(num_slots=16, max_depth=8, n_inputs=4, seed=seed)
        for depth in (1, 2, 4, 8):
            program = generator.generate(depth=depth, width=8)
            validate_program(program)
            assert max(n.depth for n in program.nodes if program.existence[n.slot]) <= depth + 1


def test_truth_table_is_exhaustively_binary() -> None:
    generator = BooleanDAGGenerator(num_slots=12, max_depth=4, n_inputs=3, seed=7)
    program = generator.generate(depth=3, width=7)
    table = program.truth_table()
    assert len(table) == 2**3
    assert set(table) <= {0, 1}
    for bits in itertools.product((0, 1), repeat=3):
        assert program.evaluate(bits) in (0, 1)


def test_commutative_permutation_relabeling_preserves_function() -> None:
    generator = BooleanDAGGenerator(num_slots=14, max_depth=5, n_inputs=4, seed=19)
    program = generator.generate(depth=4, width=8)
    swapped = relabel_operands(program)
    assert program.truth_table() == swapped.truth_table()


def test_fixed_superset_contains_real_distractors() -> None:
    generator = BooleanDAGGenerator(num_slots=16, max_depth=5, n_inputs=4, seed=3)
    program = generator.generate(depth=5, width=8)
    assert program.distractor_edge_set
    assert program.true_edge_set < program.admissible_edge_set


def test_copy_mask_is_not_the_oracle() -> None:
    generator = BooleanDAGGenerator(num_slots=16, max_depth=6, n_inputs=4, seed=11)
    program = generator.generate(depth=6, width=8)
    copy_mask = program.admissible_edge_set
    assert copy_mask != program.true_edge_set


def test_inactive_slots_are_never_true_edges() -> None:
    generator = BooleanDAGGenerator(num_slots=20, max_depth=4, n_inputs=3, seed=21)
    program = generator.generate(depth=4, width=7)
    for edge in program.edges:
        assert program.existence[edge.src] == 1
        assert program.existence[edge.dst] == 1


def test_binary_operators_have_exactly_two_inputs() -> None:
    generator = BooleanDAGGenerator(num_slots=18, max_depth=8, n_inputs=4, seed=5)
    for _ in range(20):
        program = generator.generate()
        incoming = {slot: [] for slot in program.active_nodes}
        for edge in program.edges:
            incoming[edge.dst].append(edge)
        for node in program.nodes:
            assert len(incoming.get(node.slot, [])) == ARITY[node.op]


def test_invalid_cycle_is_rejected() -> None:
    nodes = (
        Node(0, Op.INPUT, 0, "input_0"),
        Node(1, Op.NOT, 1, "op_1"),
        Node(2, Op.NOT, 2, "op_2"),
        Node(3, Op.OUTPUT, 3, "output"),
    )
    program = BooleanProgram(
        nodes=nodes,
        edges=(Edge(0, 1, "arg1"), Edge(2, 1, "arg1"), Edge(1, 2, "arg1"), Edge(2, 3, "arg1")),
        inputs=(0,),
        output=3,
        existence=(1, 1, 1, 1),
        n_inputs=1,
    )
    with pytest.raises(AssertionError, match="cycle"):
        validate_program(program)
