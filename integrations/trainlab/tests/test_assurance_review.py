import base64
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from trainlab.assurance_review import verify_assurance_review
from trainlab.diagnostic_bundle import create
from trainlab.runner import LabError, digest, write_json
from trainlab.signed_bundle_review import sign_review


def assurance_fixture():
    def raw(value):
        return (json.dumps(value, sort_keys=True) + "\n").encode()

    def pin(value):
        return hashlib.sha256(value).hexdigest()

    contract = {"schema": "fixture-criteria", "minimum_updates": 2}
    contract_raw = raw(contract)
    recipe_raw = raw({"research_adequacy": {"file": "contract.json", "sha256": pin(contract_raw)}})
    plan_raw = raw({"contract": contract})
    execution_raw, capture_raw = raw({"status": "MET"}), raw({"status": "COMPLETE"})
    producer_raw = b"# public constructed test producer\n"
    record = {
        "id": "run",
        "inputs": {"producer.py": pin(producer_raw), "contract.json": pin(contract_raw)},
        "files": {
            "experiment.json": pin(recipe_raw),
            "research_adequacy.json": pin(plan_raw),
            "execution_adequacy.json": pin(execution_raw),
        },
        "artifacts": {"capture.json": pin(capture_raw)},
    }
    record_raw = raw(record)
    materials = {
        "run/run.json": record_raw,
        "run/contract.json": contract_raw,
        "run/capture.json": capture_raw,
        "run/execution_adequacy.json": execution_raw,
        "run/experiment.json": recipe_raw,
        "run/plan.json": plan_raw,
        "run/research_adequacy.json": plan_raw,
        "run/output/capture.json": capture_raw,
        "source/producer.py": producer_raw,
        "source/contract.json": contract_raw,
    }
    return {
        "schema": "research_lab.claim-assurance.v1",
        "status": "TESTED",
        "claim": {
            "protocol_id": "fixture",
            "protocol_sha256": "1" * 64,
            "scope": "constructed software control",
            "metric": "accuracy",
            "direction": "max",
            "minimum_effect": 0.1,
            "seeds": [1, 2],
            "evaluation_scope": "TRAIN_ONLY_OBSERVED_CLASSIFICATION",
            "conclusion": "BOUNDED_CONTRAST_NOT_SUPPORTED",
        },
        "evidence_pin": "2" * 64,
        "synthesis": {"status": "BOUNDED_CONTRAST_NOT_SUPPORTED"},
        "runs": [
            {
                "task_id": "task",
                "run_id": "run",
                "record_sha256": pin(record_raw),
                "contract_sha256": pin(contract_raw),
                "capture_sha256": pin(capture_raw),
                "execution_sha256": pin(execution_raw),
            }
        ],
        "replay_scope": "CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME",
        "author": "operator",
        "scientific_qualification": "NOT_QUALIFIED",
        "review_materials": {
            name: {"sha256": pin(value), "base64": base64.b64encode(value).decode("ascii")}
            for name, value in materials.items()
        },
    }


def build_assurance_bundle(root, document):
    """Construct only a public test bundle; does not establish prerequisite truth."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    source, spec = root / "assurance.json", root / "spec.json"
    write_json(source, document)
    pin = digest(source)
    write_json(
        spec,
        {
            "schema": "trainlab.diagnostic-bundle-spec.v1",
            "title": "Assurance fixture",
            "data_classification": "CONSTRUCTED_PUBLIC",
            "packs": [
                {
                    "id": "research-assurance",
                    "version": "1",
                    "applicability": "fixture",
                    "dependencies": [],
                    "cost": "tiny",
                    "evidence_requirements": [],
                    "limitations": ["Not scientific evidence"],
                }
            ],
            "findings": [
                {
                    "id": "research-assurance",
                    "pack_id": "research-assurance",
                    "kind": "conclusion",
                    "summary": "Bounded fixture conclusion",
                    "status": document["status"],
                    "evidence": {"path": "assurance.json", "sha256": pin, "pointer": []},
                    "reviews": [],
                }
            ],
        },
    )
    bundle = root / "bundle"
    manifest = create(spec, digest(spec), bundle)
    return bundle, manifest, pin


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool required")
class AssuranceReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.key = self.root / "ephemeral-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        self.trust = self.root / "allowed"
        self.trust.write_text("reviewer " + self.key.with_suffix(".pub").read_text())
        self.trust_pin = digest(self.trust)
        self.document = assurance_fixture()
        self.build()

    def build(self, verdict="accept"):
        destination = self.root / ("case" + str(len(list(self.root.glob("case*")))))
        self.bundle, self.manifest, self.pin = build_assurance_bundle(destination, self.document)
        self.envelope = destination / "signed.json"
        write_json(
            self.envelope,
            sign_review(
                self.bundle,
                self.manifest,
                signer="reviewer",
                verdict=verdict,
                note="Explicit review of exact bounded evidence, not scientific qualification",
                key_path=self.key,
            ),
        )

    def verify(self, **changes):
        kwargs = {
            "expected_evidence_sha256": self.pin,
            "author": "operator",
            "signer": "reviewer",
            "trusted_signers": self.trust,
            "trusted_signers_sha256": self.trust_pin,
        }
        kwargs.update(changes)
        return verify_assurance_review(self.bundle, self.manifest, self.envelope, **kwargs)

    def test_explicit_accept_authenticates_bounded_negative_not_scientific_pass(self):
        result = self.verify()
        self.assertEqual(result["status"], "AUTHENTICATED_ACCEPT")
        self.assertEqual(result["claim"]["conclusion"], "BOUNDED_CONTRAST_NOT_SUPPORTED")
        self.assertEqual(result["scientific_qualification"], "NOT_QUALIFIED")
        self.assertFalse(result["automatic_admission"])

    def test_negative_or_inconclusive_signed_verdict_not_acceptance(self):
        for verdict in ("request-changes", "inconclusive"):
            self.build(verdict)
            with self.assertRaisesRegex(LabError, "explicit accept"):
                self.verify()

    def test_failed_or_inconclusive_prerequisite_evidence_rejected(self):
        for status in ("FAILED", "INCONCLUSIVE"):
            self.document["status"] = status
            self.build()
            with self.assertRaises(LabError):
                self.verify()

    def test_wrong_expected_evidence_pack_or_finding_rejected(self):
        for change in (
            {"expected_evidence_sha256": "f" * 64},
            {"assurance_pack_id": "unrelated"},
            {"assurance_finding_id": "unrelated"},
        ):
            with self.assertRaises(LabError):
                self.verify(**change)

    def test_unsigned_changed_envelope_and_wrong_trust_fail(self):
        original = self.envelope.read_bytes()
        write_json(self.envelope, {"receipt": {}, "signature": ""})
        with self.assertRaises(LabError):
            self.verify()
        self.envelope.write_bytes(original)
        with self.assertRaises(LabError):
            self.verify(trusted_signers_sha256="f" * 64)
        with self.assertRaises(LabError):
            self.verify(signer="untrusted")

    def test_self_review_and_wrong_author_rejected(self):
        for author in ("reviewer", "other-author"):
            with self.assertRaises(LabError):
                self.verify(author=author)

    def test_missing_capture_or_replay_cannot_become_assurance(self):
        for field in ("capture_sha256", "execution_sha256", "contract_sha256"):
            self.document = assurance_fixture()
            del self.document["runs"][0][field]
            self.build()
            with self.assertRaises(LabError):
                self.verify()
        self.document = assurance_fixture()
        self.document["replay_scope"] = "NOT_RUN"
        self.build()
        with self.assertRaises(LabError):
            self.verify()

    def test_duplicate_runs_and_changed_source_rejected(self):
        self.document["runs"].append(copy.deepcopy(self.document["runs"][0]))
        self.build()
        with self.assertRaises(LabError):
            self.verify()
        self.document = assurance_fixture()
        self.build()
        source = next((self.bundle / "evidence").glob("*.json"))
        source.write_bytes(source.read_bytes() + b" ")
        with self.assertRaises(LabError):
            self.verify()

    def test_signature_for_different_exact_claim_cannot_be_reused(self):
        previous_envelope = self.envelope.read_bytes()
        self.document["claim"]["conclusion"] = "BOUNDED_CONTRAST_SUPPORTED"
        self.build()
        self.envelope.write_bytes(previous_envelope)
        with self.assertRaises(LabError):
            self.verify()

    def test_entire_document_binding_required_not_selected_favorable_subnode(self):
        self.document["claim"]["status"] = "TESTED"
        destination = self.root / "pointer-case"
        destination.mkdir()
        source = destination / "assurance.json"
        write_json(source, self.document)
        # Construct a valid bundle that points only to a favorable subnode.
        original_spec = next(self.root.glob("case*/spec.json"))
        spec = json.loads(original_spec.read_text())
        spec["findings"][0]["evidence"].update(sha256=digest(source), pointer=["claim"])
        path = destination / "spec.json"
        write_json(path, spec)
        self.bundle = destination / "bundle"
        self.manifest = create(path, digest(path), self.bundle)
        self.pin = digest(source)
        self.envelope = destination / "signed.json"
        write_json(
            self.envelope,
            sign_review(
                self.bundle,
                self.manifest,
                signer="reviewer",
                verdict="accept",
                note="fixture",
                key_path=self.key,
            ),
        )
        with self.assertRaises(LabError):
            self.verify()


class AssuranceMaterialTests(unittest.TestCase):
    def check(self, document):
        from trainlab.assurance_review import _assurance

        _assurance(document, "operator")

    def test_exact_source_bytes_are_available_and_bound(self):
        self.check(assurance_fixture())

    def test_missing_substantive_role_or_input_or_artifact_rejected(self):
        for name in (
            "run/contract.json",
            "run/capture.json",
            "run/plan.json",
            "source/producer.py",
            "run/output/capture.json",
            "run/research_adequacy.json",
        ):
            document = assurance_fixture()
            del document["review_materials"][name]
            with self.subTest(name=name), self.assertRaises(LabError):
                self.check(document)

    def test_strict_base64_and_corresponding_hash_required(self):
        for value in ("!", "YQ==\n", "YQ=="):
            document = assurance_fixture()
            document["review_materials"]["source/producer.py"]["base64"] = value
            with self.subTest(value=value), self.assertRaises(LabError):
                self.check(document)
        document = assurance_fixture()
        item = document["review_materials"]["run/capture.json"]
        changed = b'{"status":"CHANGED"}'
        item.update(
            sha256=hashlib.sha256(changed).hexdigest(), base64=base64.b64encode(changed).decode()
        )
        with self.assertRaisesRegex(LabError, "correspondence"):
            self.check(document)

    def test_safe_paths_and_no_unmapped_material(self):
        for name in ("../escape", "/outside", "source/../escape", "unmapped.json"):
            document = assurance_fixture()
            document["review_materials"][name] = document["review_materials"]["source/producer.py"]
            with self.subTest(name=name), self.assertRaises(LabError):
                self.check(document)

    def test_train_only_scope_cannot_become_heldout(self):
        document = assurance_fixture()
        document["claim"]["evaluation_scope"] = "HELD_OUT_GENERALIZATION"
        with self.assertRaises(LabError):
            self.check(document)

    def test_material_limit_rejects_without_silently_omitting_source(self):
        from trainlab.assurance_review import MAX_MATERIAL_BYTES

        document = assurance_fixture()
        raw = b"x" * MAX_MATERIAL_BYTES
        document["review_materials"]["source/large.py"] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode(),
        }
        with self.assertRaisesRegex(LabError, "8 MiB"):
            self.check(document)
