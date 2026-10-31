"""Graphical dataset workspace over the existing Forge release/reader boundary.

The optional GUI reuses TrainLab hosting. Core Forge imports remain independent.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hmac
import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from importlib.resources import files
from itertools import islice
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

try:
    from trainlab.runner import LabError, _constant, _pairs, contained_file, read_json, write_json
    from trainlab.server import Workspace
except ImportError as error:
    raise SystemExit(
        "Forge GUI requires the sibling TrainLab package; install forge-temporal-data[workbench]."
    ) from error

from .core import ForgeError, _spec, canonical, hash_bytes, release
from .dataset import Dataset

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_ROWS = 20_000
MAX_RELEASES = 128
MAX_JOBS = 1024
SPEC_FIELDS = {
    "dataset_id",
    "source_id",
    "source_version",
    "adapter",
    "license_id",
    "provenance_uri",
    "ai_use_allowed",
    "redistribution_allowed",
    "privacy_reviewed",
    "split_salt",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{32}", value):
        raise ForgeError("Select an existing dataset release.")
    return value


def example_source():
    """An explicitly constructed, local-only example; no network or training."""
    spec = {
        "dataset_id": "Workshop sensor observations",
        "source_id": "constructed/workshop-sensors",
        "source_version": "v1",
        "adapter": "operations-jsonl",
        "license_id": "constructed-example",
        "provenance_uri": "https://example.invalid/constructed-forge-example",
        "ai_use_allowed": True,
        "redistribution_allowed": True,
        "privacy_reviewed": True,
        "split_salt": "forge-workbench-constructed-v1",
    }
    rows = [
        {
            "episode_id": f"episode-{i}",
            "subject_id": f"machine-{i}",
            "record_id": f"record-{i}",
            "observed_at": "2026-01-01T10:00:00Z",
            "available_at": "2026-01-01T10:00:01Z",
            "observation": {"temperature": 18 + i, "pressure": round(1 + i / 100, 2)},
            "action": None,
            "outcome": {
                "status": "constructed",
                "verified": False,
                "available_at": "2026-01-02T10:00:00Z",
                "value": 2 * i + 1,
            },
        }
        for i in range(30)
    ]
    return {
        "source_name": "constructed-sensors.jsonl",
        "spec": spec,
        "source_jsonl": "".join(canonical(row).decode() for row in rows),
    }


class ForgeWorkspace(Workspace):
    brand = "Forge"
    body_limit = 12 * 1024 * 1024

    def __init__(self, root: Path, experiments=None, **options):
        super().__init__(root, None, log_limit=options.get("log_limit", 16 * 1024 * 1024))
        self.root = self.runs
        self.trainlab_url = None
        self.current_job = None
        for name in ("releases", "sources", "metadata", "jobs"):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)

    def _record(self, identity):
        identity = _id(identity)
        record = read_json(contained_file(self.root / "metadata", identity + ".json"), 65536)
        required = {
            "schema",
            "id",
            "name",
            "created_at",
            "source_name",
            "manifest_sha256",
            "records",
            "split_records",
            "integrity",
            "last_verified_at",
            "verification_error",
            "source_kind",
        }
        if (
            not isinstance(record, dict)
            or set(record) != required
            or record["id"] != identity
            or record["schema"] != "forge.workbench.release.v1"
            or not re.fullmatch("[a-f0-9]{64}", record["manifest_sha256"])
            or record["integrity"] not in ("valid", "failed")
            or any(
                not isinstance(record[k], str)
                for k in ("name", "source_name", "created_at", "source_kind")
            )
            or type(record["records"]) is not int
            or record["records"] < 0
            or not isinstance(record["last_verified_at"], str)
            or (
                record["verification_error"] is not None
                and not isinstance(record["verification_error"], str)
            )
            or record["source_kind"] not in ("CONSTRUCTED", "OPERATOR_SUPPLIED")
            or not isinstance(record["split_records"], dict)
            or set(record["split_records"]) != {"train", "validation", "test"}
            or any(type(v) is not int or v < 0 for v in record["split_records"].values())
        ):
            raise ForgeError("Saved dataset metadata is invalid.")
        return record

    def _dataset(self, identity):
        record = self._record(identity)
        return record, Dataset(
            self.root / "releases" / record["id"], manifest_sha256=record["manifest_sha256"]
        )

    def _catalog(self):
        records = []
        errors = 0
        paths = list(
            islice(
                (
                    path
                    for path in (self.root / "metadata").iterdir()
                    if not path.name.startswith(".metadata-")
                ),
                MAX_RELEASES + 1,
            )
        )
        if len(paths) > MAX_RELEASES:
            raise ForgeError("Dataset library capacity exceeded; archive the workspace offline.")
        for path in paths:
            try:
                if path.suffix != ".json":
                    raise ForgeError("Unsupported metadata")
                records.append(self._record(path.stem))
            except (OSError, ValueError, TypeError, KeyError):
                errors += 1
        return sorted(records, key=lambda row: row["created_at"], reverse=True), errors

    def _jobs(self):
        jobs = []
        paths = list((self.root / "jobs").glob("*.json"))
        if len(paths) > MAX_JOBS:
            raise ForgeError("Activity capacity exceeded; archive the workspace offline.")
        for path in paths:
            try:
                job = read_json(contained_file(self.root / "jobs", path.name), 65536)
                if (
                    not isinstance(job, dict)
                    or set(job)
                    != {"id", "name", "release_id", "status", "created_at", "finished_at", "error"}
                    or job.get("id") != path.stem
                    or job.get("status") not in ("queued", "running", "succeeded", "failed")
                    or not isinstance(job.get("name"), str)
                    or not isinstance(job.get("created_at"), str)
                    or not job["created_at"]
                    or (job["finished_at"] is not None and not isinstance(job["finished_at"], str))
                    or (job["error"] is not None and not isinstance(job["error"], str))
                ):
                    raise ForgeError("Invalid job")
                job["active"] = (
                    job["id"] == self.current_job
                    and self.active is not None
                    and not self.active.done()
                )
                jobs.append(job)
            except (OSError, ValueError, TypeError):
                jobs.append(
                    {
                        "id": path.stem,
                        "name": "Unreadable activity record",
                        "status": "failed",
                        "created_at": "",
                        "error": "An activity record is invalid.",
                    }
                )
        return sorted(jobs, key=lambda row: row["created_at"], reverse=True)

    def _profile(self, dataset):
        # Only TRAIN/VALIDATION contribute explorer fields or clock suggestions.
        # TEST bytes are verified by Dataset, but never projected to the GUI.
        rows = dataset._rows["train"] + dataset._rows["validation"]
        if not rows:
            return {
                "fields": [],
                "temporal_basis": dataset._manifest["adapter"],
                "feature_cutoff": None,
                "target_cutoff": None,
            }
        common = set(rows[0]["observation"])
        for row in rows:
            common.intersection_update(row["observation"])
        labels = [
            row["outcome"]["available_at"]
            for row in rows
            if row["outcome"]["available_at"] is not None
        ]
        return {
            "fields": sorted(key for key in common if len(key) <= 120)[:128],
            "fields_truncated": len(common) > 128,
            "temporal_basis": rows[0]["temporal_basis"],
            "feature_cutoff": max(row["available_at"] for row in rows),
            "target_cutoff": max(labels) if labels else None,
        }

    def _health(self):
        try:
            records, errors = self._catalog()
            free = shutil.disk_usage(self.root).free
        except (OSError, ValueError, TypeError, KeyError):
            return {"status": "degraded", "datasets": 0, "invalid_metadata": 1}
        return {
            "status": "degraded"
            if errors or free < 64 * 1024 * 1024 or any(r["integrity"] == "failed" for r in records)
            else "ok",
            "datasets": len(records),
            "invalid_metadata": errors,
        }

    def _submit(self, name, identity, action):
        with self.lock:
            if self.cancel.is_set():
                return 503, {"error": "Workspace is shutting down."}, "application/json"
            if self.active is not None and not self.active.done():
                return (
                    409,
                    {"error": "A dataset operation is already running. Wait for it to finish."},
                    "application/json",
                )
            if len(list((self.root / "jobs").iterdir())) >= MAX_JOBS:
                raise ForgeError("Activity capacity reached; archive this workspace offline.")
            job = {
                "id": uuid.uuid4().hex,
                "name": name,
                "release_id": identity,
                "status": "queued",
                "created_at": _now(),
                "finished_at": None,
                "error": None,
            }
            path = self.root / "jobs" / (job["id"] + ".json")
            write_json(path, job)

            def execute():
                job["status"] = "running"
                write_json(path, job)
                try:
                    if self.cancel.is_set():
                        raise ForgeError("Operation interrupted by service shutdown.")
                    action()
                    job["status"] = "succeeded"
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    OverflowError,
                    RecursionError,
                ) as error:
                    job["status"] = "failed"
                    job["error"] = (
                        str(error)[:1000]
                        if isinstance(error, (ForgeError, LabError))
                        else (
                            "Dataset operation failed. "
                            "Check the source schema and workspace permissions."
                        )
                    )
                finally:
                    job["finished_at"] = _now()
                    write_json(path, job)
                return job

            self.current_job = job["id"]
            self.active = self.pool.submit(execute)
            return 202, dict(job), "application/json"

    def _create(self, payload):
        if not isinstance(payload, dict) or set(payload) not in (
            {"source_name", "source_jsonl", "spec"},
            {"source_name", "source_base64", "spec"},
        ):
            raise ForgeError("Choose a JSONL file and complete its source specification.")
        name = payload["source_name"]
        if "source_base64" in payload:
            value = payload["source_base64"]
            if not isinstance(value, str) or len(value) > 4 * ((MAX_SOURCE_BYTES + 2) // 3):
                raise ForgeError("Upload a UTF-8 JSONL source up to 8 MiB.")
            try:
                source = base64.b64decode(value, validate=True).decode("utf-8")
            except (ValueError, UnicodeError, binascii.Error) as error:
                raise ForgeError("Source bytes must be valid UTF-8 JSONL.") from error
        else:
            source = payload["source_jsonl"]
        spec = payload["spec"]
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 120
            or "/" in name
            or "\\" in name
            or name in (".", "..")
            or any(ord(c) < 32 for c in name)
        ):
            raise ForgeError("Use a plain source filename without paths.")
        if (
            not isinstance(source, str)
            or not source.strip()
            or len(source.encode()) > MAX_SOURCE_BYTES
        ):
            raise ForgeError("Upload a nonempty UTF-8 JSONL source up to 8 MiB.")
        if len(source.splitlines()) > MAX_ROWS:
            raise ForgeError("The GUI supports at most 20,000 source records per release.")
        if not isinstance(spec, dict) or set(spec) != SPEC_FIELDS:
            raise ForgeError("Complete every required source field and rights declaration.")
        if any(
            not isinstance(spec.get(key), str) or not 1 <= len(spec[key]) <= 500
            for key in (
                "dataset_id",
                "source_id",
                "source_version",
                "license_id",
                "provenance_uri",
                "split_salt",
            )
        ):
            raise ForgeError("Source identifiers and provenance must contain 1–500 characters.")
        _spec(spec)
        records, errors = self._catalog()
        if errors:
            raise ForgeError("Repair unreadable library metadata before creating another release.")
        if len(records) >= MAX_RELEASES:
            raise ForgeError("Dataset library is full; archive it offline.")
        if shutil.disk_usage(self.root).free < 64 * 1024 * 1024:
            raise ForgeError("Workspace disk space is low. Free space before importing more data.")
        identity = uuid.uuid4().hex
        # Source and spec are captured by value before the background job starts.
        encoded = source.encode()
        frozen_spec = canonical(spec)
        spec = json.loads(frozen_spec)
        constructed = {
            "source_name": name,
            "source_jsonl": source,
            "spec": spec,
        } == example_source()

        def build():
            source_root = self.root / "sources" / identity
            source_root.mkdir(mode=0o700)
            (source_root / "source.jsonl").write_bytes(encoded)
            write_json(source_root / "spec.json", json.loads(frozen_spec))
            output = self.root / "releases" / identity
            try:
                for line in encoded.splitlines():
                    canonical(json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant))
                manifest = release(source_root / "source.jsonl", source_root / "spec.json", output)
                pin = hash_bytes((output / "manifest.json").read_bytes())
                dataset = Dataset(output, manifest_sha256=pin)
                summary = dataset.summary()
                now = _now()
                record = {
                    "schema": "forge.workbench.release.v1",
                    "id": identity,
                    "name": spec["dataset_id"],
                    "created_at": now,
                    "source_name": name,
                    "manifest_sha256": pin,
                    "records": summary["records"],
                    "split_records": summary["split_records"],
                    "integrity": "valid",
                    "last_verified_at": now,
                    "verification_error": None,
                    "source_kind": "CONSTRUCTED" if constructed else "OPERATOR_SUPPLIED",
                }
                assert manifest["records"] == record["split_records"]
                write_json(self.root / "metadata" / (identity + ".json"), record)
            except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
                # An unsuccessful staged release is not part of the library.
                if output.exists():
                    shutil.rmtree(output)
                raise

        return self._submit("Create " + spec["dataset_id"], identity, build)

    def _projection(self, payload, exporting=False):
        expected = {"id", "split", "fields", "cutoff", "target_cutoff", "offset", "limit"}
        if exporting:
            expected.add("format")
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ForgeError("Choose a release, split, feature fields and visibility cutoff.")
        if payload["split"] not in ("train", "validation"):
            raise ForgeError("The GUI withholds TEST rows. Choose train or validation.")
        if (
            not isinstance(payload["fields"], list)
            or not 1 <= len(payload["fields"]) <= 12
            or any(
                not isinstance(field, str) or not 1 <= len(field) <= 120
                for field in payload["fields"]
            )
        ):
            raise ForgeError("Select 1–12 observation feature fields.")
        if (
            type(payload["offset"]) is not int
            or not 0 <= payload["offset"] <= MAX_ROWS
            or type(payload["limit"]) is not int
            or not 1 <= payload["limit"] <= 50
        ):
            raise ForgeError("Choose a valid page of at most 50 examples.")
        record, dataset = self._dataset(payload["id"])
        relative = dataset._manifest["adapter"] == "robot-jsonl"
        if relative and any(
            type(value) is bool for value in (payload["cutoff"], payload["target_cutoff"])
        ):
            raise ForgeError("Relative cutoffs must be numeric seconds, not booleans.")
        cutoff = float(payload["cutoff"]) if relative else payload["cutoff"]
        target = payload["target_cutoff"]
        if relative and target is not None:
            target = float(target)
        rows = dataset.examples(
            payload["split"], cutoff=cutoff, feature_fields=payload["fields"], target_cutoff=target
        )
        if exporting:
            return record, rows
        start = payload["offset"]
        stop = start + payload["limit"]
        return {
            "rows": rows[start:stop],
            "total": len(rows),
            "offset": start,
            "limit": payload["limit"],
            "manifest_sha256": record["manifest_sha256"],
            "qualification": "NOT_QUALIFIED",
        }

    def dispatch(self, method, path, headers, body=b""):
        url = urlsplit(path)
        mime = "application/json"
        try:
            if method == "GET":
                assets = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/forge": ("index.html", "text/html; charset=utf-8"),
                    "/forge/": ("index.html", "text/html; charset=utf-8"),
                    "/forge/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/forge/style.css": ("style.css", "text/css; charset=utf-8"),
                }
                if url.path in assets:
                    filename, mime = assets[url.path]
                    return 200, files("forge_data").joinpath("static", filename).read_bytes(), mime
                if url.path == "/forge/shared.css":
                    return (
                        200,
                        files("trainlab").joinpath("static/style.css").read_bytes(),
                        "text/css; charset=utf-8",
                    )
                if url.path == "/healthz":
                    health = self._health()
                    return (200 if health["status"] == "ok" else 503), health, mime
                if url.path == "/api/forge/state":
                    catalog, errors = self._catalog()
                    return (
                        200,
                        {
                            "releases": catalog,
                            "jobs": self._jobs(),
                            "workspace_errors": errors,
                            "token": self.token,
                            "busy": self.active is not None and not self.active.done(),
                            "trainlab_url": self.trainlab_url,
                        },
                        mime,
                    )
                if url.path == "/api/forge/example":
                    return 200, example_source(), mime
                query = parse_qs(url.query)
                if url.path in ("/api/forge/detail", "/api/forge/manifest"):
                    record, dataset = self._dataset(query.get("id", [""])[0])
                    if url.path.endswith("/manifest"):
                        return 200, canonical(dataset._manifest), "application/octet-stream"
                    return (
                        200,
                        {
                            **record,
                            "manifest": dataset._manifest,
                            "profile": self._profile(dataset),
                        },
                        mime,
                    )
                return 404, {"error": "Not found."}, mime
            if method != "POST":
                return 405, {"error": "Method not allowed."}, mime
            if not hmac.compare_digest(headers.get("X-TrainLab-Token", ""), self.token):
                return 403, {"error": "A same-origin session token is required."}, mime
            if (
                headers.get("Content-Type") != "application/json"
                or not 0 < len(body) <= self.body_limit
            ):
                raise ForgeError("A bounded JSON request is required.")
            payload = json.loads(body, object_pairs_hook=_pairs, parse_constant=_constant)
            if url.path == "/api/forge/releases":
                return self._create(payload)
            if url.path == "/api/forge/preview":
                return 200, self._projection(payload), mime
            if url.path == "/api/forge/export":
                record, rows = self._projection(payload, exporting=True)
                if payload["format"] == "jsonl":
                    return 200, b"".join(canonical(row) for row in rows), "application/x-ndjson"
                if payload["format"] != "csv":
                    raise ForgeError("Choose CSV or JSONL export.")
                output = io.StringIO()
                writer = csv.writer(output)
                fields = payload["fields"]

                def safe(value):
                    text = "" if value is None else str(value)
                    return "'" + text if re.match(r"^(?:\s*[=+@\-]|[\t\r\n])", text) else text

                writer.writerow(
                    [
                        "record_id",
                        "subject_id",
                        *("feature." + field for field in fields),
                        "target",
                        "target_verified",
                    ]
                )
                for row in rows:
                    target = row["target"]
                    values = [
                        row["record_id"],
                        row["subject_id"],
                        *(
                            json.dumps(row["features"][field], ensure_ascii=False)
                            if isinstance(row["features"][field], (dict, list))
                            else row["features"][field]
                            for field in fields
                        ),
                        target.get("value") if target else None,
                        target["verified"] if target else None,
                    ]
                    writer.writerow([safe(value) for value in values])
                return 200, output.getvalue().encode(), "text/csv; charset=utf-8"
            if url.path == "/api/forge/verify":
                if not isinstance(payload, dict) or set(payload) != {"id"}:
                    raise ForgeError("Select a release to verify.")
                record = self._record(payload["id"])

                def verify():
                    try:
                        self._dataset(record["id"])
                        record.update(integrity="valid", verification_error=None)
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        record.update(
                            integrity="failed",
                            verification_error=(
                                "Release bytes or metadata no longer match their saved identity."
                            ),
                        )
                        raise ForgeError(record["verification_error"]) from error
                    finally:
                        record["last_verified_at"] = _now()
                        write_json(self.root / "metadata" / (record["id"] + ".json"), record)

                return self._submit("Verify " + record["name"], record["id"], verify)
            if url.path == "/api/forge/compare":
                if (
                    not isinstance(payload, dict)
                    or set(payload) != {"ids"}
                    or not isinstance(payload["ids"], list)
                    or not 2 <= len(payload["ids"]) <= 8
                    or any(not isinstance(x, str) for x in payload["ids"])
                    or len(set(payload["ids"])) != len(payload["ids"])
                ):
                    raise ForgeError("Select 2–8 distinct releases to compare.")
                pairs = [self._dataset(identity) for identity in payload["ids"]]
                comparisons = [
                    {**record, "manifest": dataset._manifest} for record, dataset in pairs
                ]
                keys = (
                    "source_id",
                    "source_version",
                    "source_sha256",
                    "source_spec_sha256",
                    "adapter",
                    "split_salt",
                    "license_id",
                )
                differences = [
                    key
                    for key in keys
                    if any(
                        row["manifest"][key] != comparisons[0]["manifest"][key]
                        for row in comparisons[1:]
                    )
                ]
                return (
                    200,
                    {
                        "releases": comparisons,
                        "differences": differences,
                        "qualification": "NOT_QUALIFIED",
                    },
                    mime,
                )
            return 404, {"error": "Not found."}, mime
        except (ForgeError, LabError) as error:
            return 400, {"error": str(error)[:1000]}, "application/json"
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
            return (
                400,
                {
                    "error": (
                        "Dataset request could not be completed. "
                        "Check its fields, release integrity and workspace permissions."
                    )
                },
                "application/json",
            )


def main():
    from trainlab.production import serve_production
    from trainlab.server import Dashboard

    parser = argparse.ArgumentParser(description="Forge graphical dataset workbench")
    parser.add_argument("--workspace", type=Path, default=Path(".forge"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--auth-file", type=Path)
    parser.add_argument("--public-origin")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    try:
        if args.production:
            serve_production(
                args.workspace,
                None,
                auth_file=args.auth_file,
                public_origin=args.public_origin,
                host=args.host,
                port=args.port,
                workspace_factory=ForgeWorkspace,
            )
        else:
            if args.auth_file or args.public_origin or args.host != "127.0.0.1":
                raise ForgeError("Remote hosting options require --production.")
            with Dashboard(
                args.workspace, None, args.port, workspace_factory=ForgeWorkspace
            ) as server:
                print(f"Forge: http://127.0.0.1:{server.server_port}/forge/", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
    except (ForgeError, LabError, OSError, ValueError) as error:
        parser.exit(2, f"forge-workbench: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
