from investigation_world.frontier.diversity import compute_task_diversity


def _shallow_task(seed: int, split: str = "train") -> dict:
    return {
        "task_id": f"seed-{seed}",
        "seed": seed,
        "split": split,
        "source_family": "single-source",
        "grammar_family": "one-shallow-grammar",
        "workflow_topology": "read>classify",
        "action_sequence": ["read", "classify"],
        "failure_mode": "parser",
        "verifier_conditions": ["label_match"],
        "artifact_schema": "incident-v1",
        "components": ["incident", "classifier"],
        "prompt": f"Inspect incident {seed} and choose one label.",
    }


def _heterogeneous_tasks(count: int = 48) -> list[dict]:
    tasks = []
    for i in range(count):
        family = i % 8
        topology = i % 6
        failure = i % 5
        schema = i % 4
        verifier = i % 7
        tasks.append(
            {
                "task_id": f"hetero-{i}",
                "split": "train" if i % 3 else "private_test",
                "source_family": f"source-{family}",
                "grammar_family": f"grammar-{i % 8}",
                "workflow_topology": f"topology-{topology}>branch-{i % 3}>finish-{i % 5}",
                "action_sequence": [f"tool-{i % 9}", f"action-{i % 11}", f"finish-{i % 5}"],
                "failure_mode": f"failure-{failure}",
                "verifier_conditions": [f"verify-{verifier}", f"guard-{i % 4}"],
                "artifact_schema": f"schema-{schema}",
                "components": [f"component-{i % 12}", f"component-{(i * 5 + 3) % 17}"],
                "prompt": (
                    f"Workflow family {family} operation {i} "
                    f"topology {topology} schema {schema}"
                ),
            }
        )
    return tasks


def test_diversity_report_identity_and_calculations_are_deterministic():
    tasks = _heterogeneous_tasks()
    first = compute_task_diversity(tasks, benchmark_name="fixture", candidate_id="C-1")
    second = compute_task_diversity(tasks, benchmark_name="fixture", candidate_id="C-1")
    assert first == second
    assert first.report_id == second.report_id


def test_ten_thousand_near_duplicate_seeds_cannot_fake_diversity():
    report = compute_task_diversity([_shallow_task(i) for i in range(10_000)])
    assert report.raw_task_count == 10_000
    assert report.effective_diversity <= 1.01
    assert report.near_duplicate_share > 0.999
    assert report.largest_cluster_share > 0.99
    assert report.dimensions["source_family"].normalized_entropy == 0.0


def test_one_shallow_grammar_has_high_concentration():
    report = compute_task_diversity([_shallow_task(i) for i in range(100)])
    assert report.dimensions["grammar_family"].category_count == 1
    assert report.dimensions["grammar_family"].largest_category_share == 1.0
    assert report.source_concentration == 1.0


def test_heterogeneous_structures_have_higher_effective_diversity():
    shallow = compute_task_diversity([_shallow_task(i) for i in range(120)])
    heterogeneous = compute_task_diversity(_heterogeneous_tasks(120))
    assert heterogeneous.effective_diversity > shallow.effective_diversity
    assert heterogeneous.cluster_count > shallow.cluster_count
    assert heterogeneous.largest_cluster_share < shallow.largest_cluster_share


def test_one_shallow_grammar_is_exposed_even_when_other_metadata_varies():
    from investigation_world.frontier.models import FrontierQualificationPolicy, GateStatus
    from investigation_world.frontier.qualification import task_diversity_gate

    tasks = _heterogeneous_tasks(96)
    for task in tasks:
        task["grammar_family"] = "one-shallow-grammar"
    report = compute_task_diversity(tasks)
    gate = task_diversity_gate(report, FrontierQualificationPolicy())
    assert report.dimensions["grammar_family"].largest_category_share == 1.0
    assert gate.status is GateStatus.FAIL
    assert gate.observed["maximum_dimension_concentration"] == 1.0
