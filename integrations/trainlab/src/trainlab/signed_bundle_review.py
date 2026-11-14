"""Create and verify an offline signed review for exact diagnostic evidence."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .diagnostic_bundle import _parse, _verified
from .prediction_artifacts import _bytes, _hash, _require, _text
from .runner import LabError

NAMESPACE = "veritas-diagnostic-review-v1"
SCHEMA = "trainlab.signed-bundle-review.v1"
VERDICTS = ("accept", "request-changes", "inconclusive")


def _read(path, limit):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "regular local file required")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _require(0 < len(raw) <= limit, "signed review file size out of bounds")
    return raw


def _identity(signer):
    _require(
        type(signer) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}", signer),
        "invalid exact signer identity",
    )


def _reviewed(root, pin):
    snapshot, _ = _verified(root, pin)
    bundle = _parse(snapshot["bundle.json"])
    _require(
        type(bundle) is dict
        and bundle.get("schema") == "trainlab.diagnostic-bundle.v1"
        and type(bundle.get("packs")) is list
        and 1 <= len(bundle["packs"]) <= 64,
        "invalid reviewed bundle metadata",
    )
    result, seen = [], set()
    for pack in bundle["packs"]:
        _require(
            type(pack) is dict
            and _text(pack.get("id"))
            and _text(pack.get("version"))
            and pack["id"] not in seen,
            "invalid or duplicate reviewed pack",
        )
        seen.add(pack["id"])
        result.append({"id": pack["id"], "version": pack["version"]})
    return result


def _receipt(packs, manifest, signer, verdict, note):
    _identity(signer)
    _require(
        verdict in VERDICTS and _text(note) and len(note) <= 2000,
        "bounded signed verdict and note required",
    )
    payload = {
        "schema": SCHEMA,
        "manifest_sha256": manifest,
        "signer": signer,
        "verdict": verdict,
        "note": note,
        "packs": packs,
    }
    _require(len(_bytes(payload)) <= 128 * 1024, "signed receipt is too large")
    return payload


def _ssh(args, *, body, directory):
    executable = shutil.which("ssh-keygen")
    _require(executable is not None, "OpenSSH ssh-keygen is required")
    try:
        result = subprocess.run(
            [executable, "-Y", *args],
            input=body,
            capture_output=True,
            check=False,
            cwd=directory,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabError("OpenSSH signature operation could not complete") from exc
    _require(result.returncode == 0, "OpenSSH signature operation rejected the receipt or key")
    return result.stdout


def sign_review(root, manifest_sha256, *, signer, verdict, note, key_path):
    """Sign explicit receipt bytes using a caller-selected local SSH private key."""
    packs = _reviewed(root, manifest_sha256)
    receipt = _receipt(packs, manifest_sha256, signer, verdict, note)
    key = Path(key_path).absolute()
    _require(key.is_file() and not key.is_symlink(), "regular local signing key required")
    with tempfile.TemporaryDirectory(prefix="veritas-review-") as temp:
        message = _bytes(receipt)
        signature = _ssh(["sign", "-f", str(key), "-n", NAMESPACE], body=message, directory=temp)
    _require(0 < len(signature) <= 8192, "invalid signature size")
    return {"receipt": receipt, "signature": base64.b64encode(signature).decode("ascii")}


def verify_review(
    root, manifest_sha256, envelope_path, *, signer, trusted_signers, trusted_signers_sha256
):
    """Verify one exact identity against a separately pinned local trust file."""
    _identity(signer)
    envelope = _parse(_read(envelope_path, 1024 * 1024))
    _require(
        type(envelope) is dict and set(envelope) == {"receipt", "signature"},
        "invalid signed review envelope",
    )
    claimed = envelope["receipt"]
    _require(
        type(claimed) is dict
        and set(claimed) == {"schema", "manifest_sha256", "signer", "verdict", "note", "packs"},
        "invalid signed review fields",
    )
    packs = _reviewed(root, manifest_sha256)
    expected = _receipt(packs, manifest_sha256, signer, claimed["verdict"], claimed["note"])
    _require(_bytes(expected) == _bytes(claimed), "receipt does not match expected review context")
    armor = envelope["signature"]
    _require(type(armor) is str and 0 < len(armor) <= 11000, "invalid signature encoding")
    try:
        signature = base64.b64decode(armor, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LabError("invalid signature encoding") from exc
    _require(0 < len(signature) <= 8192, "invalid signature size")
    _require(_hash(trusted_signers_sha256), "exact allowed-signers pin required")
    trust = _read(trusted_signers, 64 * 1024)
    _require(
        hashlib.sha256(trust).hexdigest() == trusted_signers_sha256, "allowed-signers hash mismatch"
    )
    with tempfile.TemporaryDirectory(prefix="veritas-review-verify-") as temp:
        directory = Path(temp)
        (directory / "allowed").write_bytes(trust)
        (directory / "signature").write_bytes(signature)
        _ssh(
            ["verify", "-f", "allowed", "-I", signer, "-n", NAMESPACE, "-s", "signature"],
            body=_bytes(expected),
            directory=temp,
        )
    return {
        "valid": True,
        "receipt": expected,
        "namespace": NAMESPACE,
        "trusted_signers_sha256": trusted_signers_sha256,
        "scope": "Verified local signature and exact bundle bytes.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sign = commands.add_parser("sign")
    sign.add_argument("--key", type=Path, required=True)
    sign.add_argument("--verdict", choices=VERDICTS, required=True)
    sign.add_argument("--note", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--envelope", type=Path, required=True)
    verify.add_argument("--allowed-signers", type=Path, required=True)
    verify.add_argument("--allowed-signers-sha256", required=True)
    for command in (sign, verify):
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        command.add_argument("--signer", required=True)
    args = parser.parse_args()
    try:
        if args.command == "sign":
            result = sign_review(
                args.root,
                args.manifest_sha256,
                signer=args.signer,
                verdict=args.verdict,
                note=args.note,
                key_path=args.key,
            )
        else:
            result = verify_review(
                args.root,
                args.manifest_sha256,
                args.envelope,
                signer=args.signer,
                trusted_signers=args.allowed_signers,
                trusted_signers_sha256=args.allowed_signers_sha256,
            )
    except (LabError, OSError) as exc:
        parser.exit(2, f"signed review: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
