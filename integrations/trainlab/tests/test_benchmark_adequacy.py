import copy
import tempfile
import unittest
from pathlib import Path

from trainlab.benchmark_adequacy import project_benchmark
from trainlab.benchmark_execution import execute, freeze_panel
from trainlab.runner import LabError, read_json


def benchmark_fixture(root, *, alias=False, max_calls=384):
    """Constructed direct/alias contrast with equal aggregate group coverage."""

    def forward(case):
        values, links = {}, {}
        for op, key, value in case["events"]:
            links.pop(key, None)
            if op == "LINK":
                values.pop(key, None)
                links[key] = value
            elif op == "COPY":
                values[key] = values.get(value)  # Deliberately does not resolve aliases.
            else:
                values[key] = value
        return values.get(links.get(case["query"], case["query"]))

    def backward(case):
        def lookup(key, events):
            for i in range(len(events) - 1, -1, -1):
                op, target, value = events[i]
                if target == key:
                    return (
                        value
                        if op == "SET"
                        else lookup(value, events[:i] if op == "COPY" else events)
                    )
            return None

        return lookup(case["query"], case["events"])

    def shortcut(case):
        return next(v for op, _, v in reversed(case["events"]) if op == "SET")

    rows = []
    for group, before, after in [("a", "red", "blue"), ("b", "gold", "green")]:
        for op in ["COPY", "LINK"]:
            events = [["SET", "source", before], [op, "saved", "source"], ["SET", "noise", "noise"]]
            rows.append(
                {
                    "id": group + op,
                    "group": group,
                    "original": {"events": events, "query": "saved"},
                    "intervened": {"events": events + [["SET", "source", after]], "query": "saved"},
                    "expected_original": before,
                    "expected_intervened": before if op == "COPY" else after,
                    "expect_change": op == "LINK",
                }
            )
        events = [
            ["SET", "source", before],
            ["LINK", "alias", "source"],
            ["COPY", "snapshot", "alias" if alias else "source"],
        ]
        rows.append(
            {
                "id": group + "probe",
                "group": group,
                "original": {"events": events, "query": "snapshot"},
                "intervened": {"events": events + [["SET", "source", after]], "query": "snapshot"},
                "expected_original": before,
                "expected_intervened": before,
                "expect_change": False,
            }
        )
    frozen = freeze_panel(
        rows,
        source_sha256={"reference_a": "a" * 64, "reference_b": "b" * 64, "shortcut": "c" * 64},
        minimum_changed_groups=2,
        minimum_invariant_groups=2,
        maximum_shortcut_accuracy=0.5,
    )
    report = execute(
        root,
        {"reference_a": forward, "reference_b": backward, "shortcut": shortcut},
        **frozen,
        max_calls=max_calls,
    )
    return frozen, report, read_json(root / "report.json")


class BenchmarkAdequacyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.good = benchmark_fixture(self.root / "direct")

    def test_matched_counts_cannot_conceal_alias_failure(self):
        bad = benchmark_fixture(self.root / "alias", alias=True)
        self.assertEqual(self.good[1]["summary"], bad[1]["summary"])
        self.assertEqual(project_benchmark(*self.good)["admissible"], 1)
        projection = project_benchmark(*bad)
        self.assertEqual(projection["admissible"], 0)
        self.assertEqual(projection["findings_count"], 8)
        self.assertEqual(projection["failed"], 1)

    def test_partial_execution_is_not_admissible(self):
        partial = benchmark_fixture(self.root / "partial", max_calls=2)
        result = project_benchmark(*partial)
        self.assertEqual(result["admissible"], 0)
        self.assertEqual(result["complete"], 0)
        self.assertEqual(result["observed_invocations"], 2)

    def test_failure_cannot_be_relabelled_or_findings_removed(self):
        fixture = benchmark_fixture(self.root / "alias", alias=True)
        for key, value in [("status", "TESTED"), ("findings", [])]:
            altered = copy.deepcopy(fixture)
            altered[1][key] = value
            with self.subTest(key=key), self.assertRaises(LabError):
                project_benchmark(*altered)

    def test_identity_row_and_attempt_mutations_rejected(self):
        mutations = [
            lambda f: f[0]["panel"]["rows"][0].update(expected_original="tampered"),
            lambda f: f[1]["observations"].pop(),
            lambda f: f[1]["observations"].__setitem__(1, copy.deepcopy(f[1]["observations"][0])),
            lambda f: f[1]["observations"][0].update(output_sha256=None),
            lambda f: f[2]["identities"].update(configuration="0" * 64),
            lambda f: f[2]["attempts"].pop(),
            lambda f: f[2]["attempts"][0].update(status="FAILED"),
            lambda f: f[2]["coverage"][0].update(status="FAILED"),
            lambda f: f[2]["coverage"][0]["observation"]["metrics"].update(observed=1),
        ]
        for i, mutate in enumerate(mutations):
            altered = copy.deepcopy(self.good)
            mutate(altered)
            with self.subTest(mutation=i), self.assertRaises(LabError):
                project_benchmark(*altered)

    def test_partial_workbench_cannot_admit_complete_outcomes(self):
        altered = copy.deepcopy(self.good)
        altered[2]["state"] = "PARTIAL"
        self.assertEqual(project_benchmark(*altered)["admissible"], 0)


if __name__ == "__main__":
    unittest.main()
