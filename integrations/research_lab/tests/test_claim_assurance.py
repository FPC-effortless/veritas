"""Real constructed Forge -> measured TrainLab -> replay -> signed scoped review.

Ephemeral test keys are not production reviewer identities or human independence.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_lab.claim_assurance import claim_evidence
from research_lab.core import Controller
from research_lab.execution import evidence_pin, run_worker
from trainlab.research_adequacy import DIMENSIONS, recipe_identity
from trainlab.runner import digest, write_json
from trainlab.signed_bundle_review import sign_review


@unittest.skipUnless(
    importlib.util.find_spec("torch") and shutil.which("ssh-keygen"),
    "optional native Torch and OpenSSH required",
)
class ClaimAssuranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from forge_data.core import canonical, release
        from forge_data.dataset import Dataset

        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.recipes = cls.root / "recipes"
        cls.recipes.mkdir()
        spec = {
            "dataset_id": "assurance-fixture",
            "source_id": "constructed/assurance",
            "source_version": "1",
            "adapter": "operations-jsonl",
            "license_id": "constructed",
            "provenance_uri": "https://example.invalid/fixture",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "assurance-fixed",
        }
        write_json(cls.root / "source-spec.json", spec)
        rows = [
            {
                "episode_id": f"ep-{i}",
                "subject_id": str(i),
                "record_id": str(i),
                "observed_at": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:01Z",
                "observation": {"x": [float(i % 2), float(1 - i % 2)]},
                "action": None,
                "outcome": {
                    "status": "completed",
                    "value": i % 2,
                    "verified": True,
                    "available_at": "2026-01-01T00:00:02Z",
                },
            }
            for i in range(12)
        ]
        (cls.root / "source.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
        release(cls.root / "source.jsonl", cls.root / "source-spec.json", cls.root / "release")
        manifest_pin = digest(cls.root / "release/manifest.json")
        # This release is entirely constructed/authorized, not a protected TEST panel.
        data = Dataset(cls.root / "release", manifest_sha256=manifest_pin)
        examples = data.examples(
            "train",
            cutoff="2026-01-01T00:00:01Z",
            target_cutoff="2026-01-01T00:00:02Z",
            feature_fields=["x"],
        )
        write_json(
            cls.recipes / "train.json",
            {
                "schema": "trainlab.forge-train-export.v1",
                "split": "train",
                "forge_manifest_sha256": manifest_pin,
                "feature_field": "x",
                "classes": 2,
                "examples": examples,
            },
        )
        shutil.copyfile(cls.root / "release/manifest.json", cls.recipes / "forge-manifest.json")
        script = """import os
from pathlib import Path
import torch
from trainlab.adequacy_capture import capture_training
from trainlab.runner import read_json,write_json
out=Path(os.environ['TRAINLAB_OUTPUT_DIR'])
c=read_json(out.parent/'experiment.json')
torch.set_num_threads(1)
torch.manual_seed(c['seed'])
model=torch.nn.Linear(2,2)
receipt,capture=capture_training(c,Path.cwd(),data_file='train.json',producer_file='producer.py',
    model=model,steps=4,batch_size=4,learning_rate=.1,seed=c['seed'])
write_json(out/'observations.json',receipt)
write_json(out/'capture.json',capture)
rows=read_json(Path('train.json'))['examples']
x=torch.tensor([r['features']['x'] for r in rows],dtype=torch.float32)
y=torch.tensor([r['target']['value'] for r in rows])
with torch.no_grad(): pred=model(x).argmax(-1)
write_json(out/'metrics.json',{'accuracy':int((pred==y).sum())/len(rows)})
write_json(out/'predictions.json',{'predictions':pred.tolist()})
"""
        (cls.recipes / "producer.py").write_text(script)
        observed = {"parameters": 6, "steps": 4, "training_rows": len(examples), "batch_size": 4}
        write_json(cls.recipes / "prerequisites.json", observed)
        inputs = ["producer.py", "train.json", "forge-manifest.json", "prerequisites.json"]
        field_map = dict(zip(DIMENSIONS, ("parameters", "steps", "training_rows", "batch_size")))
        mappings = {arm: {} for arm in ("candidate", "control")}
        for arm in mappings:
            for seed in (1, 2, 3):
                filename, contractfile = f"{arm}-{seed}.json", f"adequacy-{arm}-{seed}.json"
                cfg = {
                    "schema": "trainlab.experiment.v1",
                    "execution_purpose": "research",
                    "name": f"{arm}-{seed}",
                    "description": "Constructed assurance acceptance",
                    "command": [sys.executable, "producer.py"],
                    "seed": seed,
                    "timeout_seconds": 30,
                    "source_kind": "CONSTRUCTED",
                    "split_identity": manifest_pin,
                    "inputs": inputs + [contractfile],
                    "artifacts": ["observations.json", "capture.json", "predictions.json"],
                    "metrics": {"accuracy": "max"},
                    "budget": {"updates": 4},
                }
                contract = {
                    "schema": "trainlab.research-adequacy.v1",
                    "claim": "fixed four-step comparison",
                    "claim_kind": "fixed_budget_comparison",
                    "scope": "constructed training-only fixture",
                    "excluded_claims": (
                        "No generalization, scientific novelty or architecture advantage"
                    ),
                    "recipe_sha256": recipe_identity(cfg),
                    "inputs": {n: digest(cls.recipes / n) for n in inputs},
                    "review": {
                        "author": "designer",
                        "reviewer": "preflight-reviewer",
                        "basis": "software acceptance of exact finite configuration",
                        "criteria_frozen_before_evaluation": True,
                    },
                    "dimensions": {
                        d: {
                            "configuration": "fixed constructed fixture",
                            "justification": "finite known software acceptance setup",
                            "limitations": "not empirical model sufficiency",
                            "criteria": [
                                {
                                    "id": "setup",
                                    "rationale": "exact setup",
                                    "evidence": "prerequisites.json",
                                    "field": f,
                                    "operator": "eq",
                                    "threshold": observed[f],
                                }
                            ],
                        }
                        for d, f in field_map.items()
                    },
                    "capture": {
                        "artifact": "capture.json",
                        "adapter": "pytorch_cpu_classification_v1",
                        "metric": "accuracy",
                    },
                    "execution": {
                        "artifact": "observations.json",
                        "dimensions": {
                            d: [
                                {
                                    "field": "optimizer_updates" if f == "steps" else f,
                                    "operator": "eq",
                                    "threshold": observed[f],
                                    "rationale": "actual executed counter",
                                }
                            ]
                            for d, f in field_map.items()
                        },
                    },
                }
                write_json(cls.recipes / contractfile, contract)
                cfg["research_adequacy"] = {
                    "file": contractfile,
                    "sha256": digest(cls.recipes / contractfile),
                }
                write_json(cls.recipes / filename, cfg)
                mappings[arm][str(seed)] = filename
        cls.lab = Controller(cls.root / "lab")
        cls.lab.program("p", "constructed measured assurance acceptance", 720, 0)
        cls.lab.resource("cpu", "cpu", 1, 0)
        protocol = {
            "schema": "research_lab.protocol.v1",
            "id": "assured",
            "program": "p",
            "author": "designer",
            "question": "Do identical pipelines differ?",
            "hypothesis": "Candidate improves",
            "alternatives": ["same", "noise"],
            "predictions": ["gain", "replay"],
            "controls": ["same seed"],
            "ablations": ["same model"],
            "metric": "accuracy",
            "direction": "max",
            "minimum_effect": 0.1,
            "seeds": [1, 2, 3],
            "resource": "cpu",
            "slots": 1,
            "max_attempts": 1,
            "stopping_rule": "all fixed seeds",
            "scope": "SYNTHETIC_RESEARCH",
            "priority": 1,
            "source_commit": "a" * 40,
            "limitations": ["training-only constructed software acceptance"],
            "next_test": "none",
            "candidate": "candidate-1.json",
            "control": "control-1.json",
            "seed_recipes": mappings,
            "replication_tolerance": 0,
            "replay_artifacts": ["predictions.json"],
        }
        cls.lab.register(protocol, cls.recipes)
        cls.lab.worker("trainer", "experiment", "cpu")
        run_worker(cls.lab, "trainer")
        cls.lab.worker("replicator", "replication", "cpu")
        run_worker(cls.lab, "replicator")
        cls.lab.worker("reviewer", "review", "cpu")
        task = cls.lab.claim("reviewer")
        if task is None:
            raise AssertionError(cls.lab.status())
        cls.lab.finish(
            task["id"],
            task["token"],
            "succeeded",
            {
                "evidence_pin": evidence_pin(cls.lab, "assured"),
                "verdict": "clean",
                "findings": [],
                "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
                "summary": "constructed test review",
            },
            0.01,
        )
        cls.package = cls.lab.prepare_claim_review(
            "assured", cls.root / "review-package", data_classification="CONSTRUCTED_PUBLIC"
        )
        cls.key = cls.root / "ephemeral-test-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cls.key)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        cls.trust = cls.root / "recipient-trust"
        cls.trust.write_text("signed-reviewer " + cls.key.with_suffix(".pub").read_text())

    def promotion(self, verdict="accept"):
        envelope = sign_review(
            self.package["bundle"],
            self.package["manifest_sha256"],
            signer="signed-reviewer",
            verdict=verdict,
            note="Ephemeral-key constructed acceptance, not real human review",
            key_path=self.key,
        )
        path = self.root / "review-envelope.json"
        write_json(path, envelope)
        return self.lab.promote_claim(
            "assured",
            self.package["bundle"],
            self.package["manifest_sha256"],
            path,
            signer="signed-reviewer",
            trusted_signers=self.trust,
            trusted_signers_sha256=digest(self.trust),
        )

    def test_measured_replayed_signed_negative_stays_negative(self):
        evidence = claim_evidence(self.lab, "assured")
        self.assertEqual(len(evidence["runs"]), 12)
        report = self.promotion()
        self.assertEqual(report["status"], "SCOPED_CLAIM_REVIEWED")
        self.assertEqual(report["claim"]["conclusion"], "BOUNDED_CONTRAST_NOT_SUPPORTED")
        self.assertEqual(report["scientific_qualification"], "NOT_QUALIFIED")

    def test_signed_inconclusive_cannot_promote(self):
        with self.assertRaises(ValueError):
            self.promotion("inconclusive")

    def test_changed_capture_blocks_previously_accepted_claim(self):
        run = claim_evidence(self.lab, "assured")["runs"][0]
        path = self.lab.root / "runs" / run["run_id"] / "output/capture.json"
        original = path.read_bytes()
        try:
            path.write_text("{}")
            with self.assertRaises(ValueError):
                self.promotion()
        finally:
            path.write_bytes(original)

    def test_forged_quality_metric_rejected_despite_rehashed_files(self):
        from trainlab.runner import read_json, verify_run

        run = claim_evidence(self.lab, "assured")["runs"][0]
        directory = self.lab.root / "runs" / run["run_id"]
        paths = [directory / "run.json", directory / "output/metrics.json"]
        originals = [p.read_bytes() for p in paths]
        try:
            record = read_json(paths[0])
            record["metrics"]["accuracy"] = 0.12345
            write_json(paths[1], record["metrics"])
            record["files"]["output/metrics.json"] = digest(paths[1])
            write_json(paths[0], record)
            self.assertFalse(verify_run(directory)["valid"])
        finally:
            for p, raw in zip(paths, originals):
                p.write_bytes(raw)

    def test_revoked_recipient_trust_cannot_revalidate(self):
        original = self.trust.read_bytes()
        try:
            self.trust.write_text("another-reviewer " + self.key.with_suffix(".pub").read_text())
            with self.assertRaises(ValueError):
                self.promotion()
        finally:
            self.trust.write_bytes(original)
