"""Constructed security and integrity tests for Forge private snapshots."""
from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError
from forge_data.dataset import Dataset
from forge_data.private_snapshot import freeze_private, verify_private

SPEC = {
    "snapshot_id": "test",
    "source_version": "1",
    "ai_use_allowed": True,
    "redistribution_allowed": False,
    "privacy_reviewed": True,
    "visibility": "operator_private",
    "purpose": "private synthetic fixture",
    "excluded_claims": "No scientific qualification",
}


class PrivateSnapshotTests(unittest.TestCase):
    def make_snapshot(self, root: Path) -> tuple[Path, str]:
        source = root / "source"
        source.mkdir()
        (source / "nested").mkdir()
        (source / "nested" / "data.txt").write_text("private", encoding="utf-8")
        destination = root / "snapshot"
        freeze_private(source, ["nested/data.txt"], SPEC, destination)
        manifest_hash = hashlib.sha256(
            (destination / "manifest.json").read_bytes()
        ).hexdigest()
        return destination, manifest_hash

    def test_private_integrity_and_public_reader_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, manifest_hash = self.make_snapshot(root)
            result = verify_private(snapshot, manifest_hash)
            self.assertTrue(result["valid"])
            self.assertFalse(result["redistribution_allowed"])
            self.assertEqual(
                result["qualification"],
                "BYTE_INTEGRITY_ONLY_NOT_SCIENTIFIC_QUALIFICATION",
            )

            with self.assertRaises(ForgeError):
                Dataset(snapshot, manifest_sha256=manifest_hash)
            with self.assertRaises(ForgeError):
                freeze_private(
                    root / "source",
                    ["nested/data.txt"],
                    SPEC,
                    snapshot,
                )

            (snapshot / "nested" / "data.txt").write_text("changed", encoding="utf-8")
            with self.assertRaises(ForgeError):
                verify_private(snapshot, manifest_hash)

    def test_no_permission_weakening_or_path_roster_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "data").write_text("private", encoding="utf-8")

            for key, value in (
                ("redistribution_allowed", True),
                ("visibility", "public"),
                ("ai_use_allowed", False),
                ("privacy_reviewed", False),
            ):
                specification = copy.deepcopy(SPEC)
                specification[key] = value
                with self.subTest(key=key):
                    with self.assertRaises(ForgeError):
                        freeze_private(source, ["data"], specification, root / key)

            invalid_rosters = (
                ["../data"],
                ["data", "data"],
                ["/tmp/data"],
                ["manifest.json"],
                [None],
                [[]],
                ["a", "a/b"],
            )
            for index, roster in enumerate(invalid_rosters):
                with self.subTest(roster=roster):
                    with self.assertRaises(ForgeError):
                        freeze_private(source, roster, SPEC, root / f"invalid-{index}")

            (source / "link").symlink_to(source / "data")
            with self.assertRaises(ForgeError):
                freeze_private(source, ["link"], SPEC, root / "symlink")

    def test_nonadjacent_prefix_collision_rejected_before_source_access(self) -> None:
        rosters = (
            ["a", "a-b", "a/b"],
            ["a/b/c", "a-b", "a"],
            ["nested/a", "nested/a-b", "nested/a/b"],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, roster in enumerate(rosters):
                with self.subTest(roster=roster):
                    destination = root / f"snapshot-{index}"
                    with self.assertRaisesRegex(ForgeError, "path collision"):
                        freeze_private(root / "missing-source", roster, SPEC, destination)
                    self.assertFalse(destination.exists())

    def test_lexical_prefix_siblings_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "a").mkdir(parents=True)
            (source / "a" / "b").write_text("nested", encoding="utf-8")
            (source / "a-b").write_text("sibling", encoding="utf-8")
            destination = root / "snapshot"
            freeze_private(source, ["a/b", "a-b"], SPEC, destination)
            manifest_hash = hashlib.sha256(
                (destination / "manifest.json").read_bytes()
            ).hexdigest()
            self.assertTrue(verify_private(destination, manifest_hash)["valid"])

    def test_manifest_rejects_duplicate_nonfinite_and_noncanonical_json(self) -> None:
        def duplicate_schema(raw: bytes) -> bytes:
            return raw.replace(
                b'"schema":"forge.private-snapshot.v1"',
                b'"schema":"forge.private-snapshot.v1","schema":"forge.private-snapshot.v1"',
                1,
            )

        def nonfinite_snapshot_id(raw: bytes) -> bytes:
            return raw.replace(b'"snapshot_id":"test"', b'"snapshot_id":NaN', 1)

        def noncanonical_whitespace(raw: bytes) -> bytes:
            return b" " + raw

        variants = (
            duplicate_schema,
            nonfinite_snapshot_id,
            noncanonical_whitespace,
        )
        for index, transform in enumerate(variants):
            with self.subTest(variant=index), tempfile.TemporaryDirectory() as directory:
                snapshot, _ = self.make_snapshot(Path(directory))
                manifest_path = snapshot / "manifest.json"
                manifest_path.write_bytes(transform(manifest_path.read_bytes()))
                changed_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                with self.assertRaises(ForgeError):
                    verify_private(snapshot, changed_hash)

    def test_verifier_rejects_extra_empty_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_hash = self.make_snapshot(Path(directory))
            (snapshot / "unlisted-empty-directory").mkdir(mode=0o700)
            with self.assertRaisesRegex(ForgeError, "files or directories"):
                verify_private(snapshot, manifest_hash)

    def test_verifier_rejects_special_files_and_permission_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot, manifest_hash = self.make_snapshot(Path(directory))
            if os.name == "posix":
                fifo = snapshot / "unexpected.fifo"
                os.mkfifo(fifo)
                with self.assertRaisesRegex(
                    ForgeError,
                    "files or directories|special filesystem",
                ):
                    verify_private(snapshot, manifest_hash)

        if os.name == "posix":
            with tempfile.TemporaryDirectory() as directory:
                snapshot, manifest_hash = self.make_snapshot(Path(directory))
                (snapshot / "nested").chmod(0o755)
                with self.assertRaisesRegex(ForgeError, "permissions"):
                    verify_private(snapshot, manifest_hash)


if __name__ == "__main__":
    unittest.main()
