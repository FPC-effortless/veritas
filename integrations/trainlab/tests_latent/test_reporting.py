import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from trainlab.latent.reporting import atlas, draw_figure, render
from trainlab.runner import read_json


class ReportingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is optional for atlas formatter validation")
    def test_atlas_csv_text_is_safe_without_changing_negative_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atlas([{"label": "observed", "coordinates": [[-1.25, 2]]}], root / "atlas.html")
            document = (root / "atlas.html").read_text()
            formatter = (
                "function csvCell" + document.split("function csvCell", 1)[1].split("\n", 1)[0]
            )
            probe = (
                formatter
                + "\nconsole.log(JSON.stringify("
                "['=1+1','\\t=2+2','@SUM(1,2)',-1.25,'ordinary'].map(csvCell)));"
            )
            process = subprocess.run(
                [shutil.which("node"), "-e", probe],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            self.assertEqual(
                json.loads(process.stdout),
                ['"\'=1+1"', '"\'\t=2+2"', '"\'@SUM(1,2)"', '"-1.25"', '"ordinary"'],
            )

    def test_csv_neutralizes_metadata_formulas_and_preserves_numeric_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("trainlab.latent.reporting.report_pdf", side_effect=ImportError):
                render(
                    {
                        "title": "constructed",
                        "identities": {"configuration": "a" * 64},
                        "jobs": [
                            {
                                "id": "score",
                                "operation": "constructed",
                                "unit": "=1+1",
                                "scope": "\t@SUM(1,2)",
                            }
                        ],
                        "figures": [],
                    },
                    {"score": {'=HYPERLINK("invalid")': -1.25}},
                    [],
                    root,
                )
            with (root / "metrics.csv").open(newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["unit"], "'=1+1")
            self.assertEqual(row["scope"], "'\t@SUM(1,2)")
            self.assertTrue(row["metric"].startswith("'="))
            self.assertEqual(row["value"], "-1.25")

    def test_declared_figure_families_have_source_based_exports(self):
        coordinates = [[0, 0], [1, 2], [2, 1]]
        fixtures = {
            "scatter": {"coordinates": coordinates},
            "trajectory": {"coordinates": coordinates},
            "heatmap": {"values": [[0, 1], [1, 0]]},
            "forest": {"point": [1, 2], "lower": [0, 1], "upper": [2, 3]},
            "curve": {"x": [1, 2, 3], "y": [2, 1, 3]},
            "spectrum": {"y": [0.7, 0.2, 0.1]},
            "reliability": {"x": [0.1, 0.9], "y": [0.2, 0.8]},
            "cdf": {"y": [2, 1, 3]},
            "stacked": {"values": [[1, -1], [2, -0.5]]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for kind, data in fixtures.items():
                with self.subTest(kind=kind):
                    names = draw_figure({"id": kind, "kind": kind, "data": data}, root)
                    self.assertEqual(len(names), 3)
                    self.assertTrue(all((root / name).stat().st_size > 100 for name in names))

    def test_atlas_preserves_row_alignment_and_escapes_script_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "atlas.html"
            attack = '</script><script>alert("input")</script>'
            result = atlas(
                [
                    {
                        "label": "view",
                        "coordinates": np.ones((2, 3)),
                        "rows": [{"id": 1, "text": attack}, {"id": 2}],
                    }
                ],
                path,
            )
            text = path.read_text()
            self.assertEqual(result["points"], 2)
            self.assertNotIn(attack, text)
            payload = text.split('<script id="data" type="application/json">', 1)[1].split(
                "</script>", 1
            )[0]
            self.assertEqual(json.loads(payload)[0]["rows"][0]["text"], attack)

    def test_failed_figure_remains_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = render(
                {
                    "title": "failure",
                    "identities": {"configuration": "a" * 64},
                    "jobs": [],
                    "figures": [{"id": "missing", "kind": "curve", "data": {}}],
                },
                {},
                [],
                root,
            )
            self.assertEqual(len(summary["figure_errors"]), 1)
            self.assertEqual(
                read_json(root / "summary.json")["figure_errors"], summary["figure_errors"]
            )
            self.assertIn("Incomplete figures", (root / "report.html").read_text())

    @unittest.skipUnless(shutil.which("node"), "Node is optional for atlas syntax validation")
    def test_generated_interactive_script_is_valid_javascript(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atlas([{"label": "observed", "coordinates": [[1, 2], [2, 1]]}], root / "atlas.html")
            script = (
                (root / "atlas.html")
                .read_text()
                .split("</script><script>", 1)[1]
                .split("</script>", 1)[0]
            )
            (root / "atlas.js").write_text(script)
            process = subprocess.run(
                [shutil.which("node"), "--check", str(root / "atlas.js")],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
