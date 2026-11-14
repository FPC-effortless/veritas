import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from trainlab.diagnostic_bundle import create
from trainlab.runner import LabError, digest, write_json
from trainlab.signed_bundle_review import sign_review, verify_review


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool required")
class SignedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.key = self.root / "key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        self.authorized = self.root / "allowed"
        self.authorized.write_text("researcher " + self.key.with_suffix(".pub").read_text())
        self.allowed_pin = digest(self.authorized)
        self.envelope = self.root / "review.json"
        self.manifest = self.build()

    def build(self):
        spec = self.root / "spec.json"
        write_json(
            spec,
            {
                "schema": "trainlab.diagnostic-bundle-spec.v1",
                "title": "Review test",
                "data_classification": "CONSTRUCTED_PUBLIC",
                "packs": [
                    {
                        "id": "control",
                        "version": "1",
                        "applicability": "fixture",
                        "dependencies": [],
                        "cost": "tiny",
                        "evidence_requirements": [],
                        "limitations": [],
                    }
                ],
                "findings": [
                    {
                        "id": "not-run",
                        "pack_id": "control",
                        "kind": "observation",
                        "summary": "Not run",
                        "status": "NOT_RUN",
                        "evidence": None,
                        "reviews": [],
                    }
                ],
            },
        )
        return create(spec, digest(spec), self.bundle)

    def sign(self):
        envelope = sign_review(
            self.bundle,
            self.manifest,
            signer="researcher",
            verdict="accept",
            note="Reviewed the exact fixture",
            key_path=self.key,
        )
        write_json(self.envelope, envelope)
        return envelope

    def verify(self, **changes):
        args = {
            "signer": "researcher",
            "trusted_signers": self.authorized,
            "trusted_signers_sha256": self.allowed_pin,
        }
        args.update(changes)
        return verify_review(self.bundle, self.manifest, self.envelope, **args)

    def test_real_signature_binds_manifest_and_pack(self):
        self.sign()
        result = self.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["receipt"]["packs"], [{"id": "control", "version": "1"}])
        self.assertEqual(result["receipt"]["manifest_sha256"], self.manifest)

    def test_changed_signed_note_or_pack_rejected(self):
        envelope = self.sign()
        envelope["receipt"]["note"] = "A different note"
        write_json(self.envelope, envelope)
        with self.assertRaises(LabError):
            self.verify()
        envelope["receipt"]["packs"][0]["version"] = "2"
        write_json(self.envelope, envelope)
        with self.assertRaises(LabError):
            self.verify()

    def test_changed_bundle_and_trust_pin_rejected(self):
        self.sign()
        with self.assertRaises(LabError):
            self.verify(signer="another-person")
        self.authorized.write_text("researcher " + self.key.with_suffix(".pub").read_text() + "\n")
        with self.assertRaises(LabError):
            self.verify()
        self.allowed_pin = hashlib.sha256(self.authorized.read_bytes()).hexdigest()
        (self.bundle / "index.html").write_text("changed")
        with self.assertRaises(LabError):
            self.verify()

    def test_untrusted_signature_rejected(self):
        self.sign()
        other = self.root / "other"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        self.authorized.write_text("researcher " + other.with_suffix(".pub").read_text())
        self.allowed_pin = digest(self.authorized)
        with self.assertRaisesRegex(LabError, "signature"):
            self.verify()
