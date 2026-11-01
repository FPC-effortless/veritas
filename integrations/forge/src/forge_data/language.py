"""Streaming, content-pinned language releases. Separate from temporal Dataset.

Rights are explicit operator declarations. Exact deduplication and long-document
MinHash screening do not establish absence of all semantic contamination.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from .core import ForgeError

KINDS = ("text", "conversation", "preference", "task")
SPLITS = ("train", "validation", "test")
MAX_ROW = 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_bytes(canonical(value) + b"\n")


def regular(root, name):
    p = Path(root) / name
    if Path(name).is_absolute() or ".." in Path(name).parts or p.is_symlink():
        raise ForgeError("invalid language release path")
    if not p.resolve().is_relative_to(Path(root).resolve()) or not p.is_file():
        raise ForgeError("missing language release file")
    if any(x.is_symlink() for x in [p, *p.parents]):
        raise ForgeError("symlink release paths unsupported")
    return p


def rows(path):
    with Path(path).open("rb") as f:
        while line := f.readline(MAX_ROW + 1):
            if len(line) > MAX_ROW:
                raise ForgeError("language row exceeds 1 MiB; shard documents upstream")
            value = json.loads(line)
            canonical(value)
            yield value


def payload(row):
    kind = row["kind"]
    if kind == "text":
        if not isinstance(row["text"], str) or not row["text"].strip():
            raise ForgeError("empty text")
        return {"text": row["text"]}
    if kind == "conversation":
        messages = row["messages"]
        if not isinstance(messages, list) or not messages:
            raise ForgeError("missing conversation")
        for msg in messages:
            if (
                set(msg) != {"role", "content"}
                or msg["role"] not in ("system", "user", "assistant", "tool")
                or not isinstance(msg["content"], str)
                or not msg["content"]
            ):
                raise ForgeError("invalid conversation message")
            if re.search(r"<\|(?:pad|bos|eos|system|user|assistant|tool|end)\|>", msg["content"]):
                raise ForgeError("literal control token in message")
        if not any(m["role"] == "assistant" for m in messages):
            raise ForgeError("conversation requires assistant target")
        return {"messages": messages}
    if kind == "preference":
        if any(not isinstance(row[k], str) or not row[k] for k in ("prompt", "chosen", "rejected")):
            raise ForgeError("invalid preference pair")
        if row["chosen"] == row["rejected"]:
            raise ForgeError("identical preference alternatives")
        return {k: row[k] for k in ("prompt", "chosen", "rejected")}
    if kind == "task":
        if row.get("verifier") == "gsm8k-exact-v1":
            if (
                not isinstance(row.get("prompt"), str)
                or not row["prompt"].strip()
                or not isinstance(row.get("expected_answer"), str)
                or not re.fullmatch(r"-?\d+(?:\.\d+)?", row["expected_answer"])
                or len(row["expected_answer"]) > 64
            ):
                raise ForgeError("invalid public GSM8K task")
            return {k: row[k] for k in ("prompt", "expected_answer", "verifier")}
        if row.get("verifier") != "integer-comparison-v1":
            raise ForgeError("unsupported public task verifier")
        if any(type(row[k]) is not int for k in ("left", "right")):
            raise ForgeError("invalid task operands")
        return {k: row[k] for k in ("prompt", "left", "right", "verifier")}
    raise ForgeError("unknown language row kind")


def _signature(text):
    words = re.findall(r"\w+", text.casefold())
    if len(words) < 80:
        return None
    shingles = {" ".join(words[i : i + 8]) for i in range(len(words) - 7)}
    return ":".join(
        str(
            min(
                int.from_bytes(
                    hashlib.blake2b((str(seed) + s).encode(), digest_size=8).digest(), "big"
                )
                for s in shingles
            )
        )
        for seed in range(4)
    )


def build_release(source, spec, destination, *, shard_bytes=8 * 1024 * 1024):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ForgeError("language releases require a new destination")
    if shard_bytes < 1024 or shard_bytes > 1024**3:
        raise ForgeError("shard size must be 1 KiB–1 GiB")
    if (
        spec.get("schema") != "forge.language-source.v1"
        or spec.get("source_sha256") != digest(source)
        or not spec.get("split_salt")
    ):
        raise ForgeError("invalid language source specification or hash")
    near_screen = spec.get("near_dedupe", "minhash4")
    if near_screen not in ("minhash4", "exact-only"):
        raise ForgeError("unsupported explicit near-duplicate screen")
    sources = spec["sources"]
    for s in sources.values():
        if (
            s.get("rights_reviewed") is not True
            or not s.get("license")
            or not s.get("provenance")
            or s.get("source_kind") not in ("CONSTRUCTED", "AUTHENTIC_CANDIDATE")
        ):
            raise ForgeError("explicit source rights and provenance required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".language-", dir=destination.parent))
    con = sqlite3.connect(temp / "index.sqlite")
    con.executescript(
        "CREATE TABLE seen (digest TEXT PRIMARY KEY);"
        "CREATE TABLE groups (name TEXT PRIMARY KEY, split TEXT);"
        "CREATE TABLE near (signature TEXT PRIMARY KEY);"
    )
    counts, rejected, files, handles = Counter(), Counter(), {}, {}
    try:
        for row in rows(source):
            if row.get("kind") not in KINDS or row.get("source_id") not in sources:
                raise ForgeError("unknown source or kind")
            group = row.get("group")
            if not isinstance(group, str) or not group:
                raise ForgeError("source grouping required")
            # Group is global: shared semantic/source groups cannot cross splits.
            score = (
                int(
                    hashlib.sha256((spec["split_salt"] + "\0" + group).encode()).hexdigest()[:8], 16
                )
                % 100
            )
            split = "train" if score < 90 else "validation" if score < 95 else "test"
            if ("split" in row) != ("upstream_split" in row):
                raise ForgeError("explicit split and upstream split must be supplied together")
            if "split" in row:
                policy = sources[row["source_id"]].get("upstream_splits")
                upstream = row.get("upstream_split")
                if (
                    not isinstance(policy, dict)
                    or upstream not in policy
                    or row["split"] not in SPLITS
                    or row["split"] not in policy[upstream]
                ):
                    raise ForgeError("upstream held-out boundary or explicit split violation")
                if upstream == "test" and row["split"] != "test":
                    raise ForgeError("upstream TEST cannot enter TRAIN or validation")
                split = row["split"]

            con.execute("INSERT OR IGNORE INTO groups VALUES (?,?)", (group, split))
            if (
                con.execute("SELECT split FROM groups WHERE name=?", (group,)).fetchone()[0]
                != split
            ):
                raise ForgeError("source group crosses splits")
            data = payload(row)
            key = hashlib.sha256(canonical(data)).hexdigest()
            try:
                con.execute("INSERT INTO seen VALUES (?)", (key,))
            except sqlite3.IntegrityError:
                rejected["exact_duplicates"] += 1
                continue
            sig = (
                _signature(data["text"])
                if row["kind"] == "text" and near_screen == "minhash4"
                else None
            )
            if sig:
                try:
                    con.execute("INSERT INTO near VALUES (?)", (sig,))
                except sqlite3.IntegrityError:
                    rejected["minhash_duplicates"] += 1
                    continue
            clean = {"kind": row["kind"], "source_id": row["source_id"], "group": group, **data}
            if "split" in row:
                clean["upstream_split"] = row["upstream_split"]
            line = canonical(clean) + b"\n"
            slot = (split, row["kind"])
            if slot not in handles or handles[slot].tell() + len(line) > shard_bytes:
                if slot in handles:
                    handles[slot].close()
                index = sum(n.startswith(f"{split}-{row['kind']}-") for n in files)
                name = f"{split}-{row['kind']}-{index:05d}.jsonl"
                files[name] = {"split": split, "kind": row["kind"], "records": 0}
                handles[slot] = (temp / name).open("wb")
            f = handles[slot]
            f.write(line)
            files[Path(f.name).name]["records"] += 1
            counts[f"{split}/{row['kind']}"] += 1
        for f in handles.values():
            f.close()
        con.close()
        (temp / "index.sqlite").unlink()
        for name, entry in files.items():
            entry.update(sha256=digest(temp / name), bytes=(temp / name).stat().st_size)
        manifest = {
            "schema": "forge.language.v1",
            "source_spec": spec,
            "files": files,
            "counts": dict(counts),
            "rejected": dict(rejected),
            "split_method": (
                "source-declared-upstream-boundaries-plus-global-group-v1"
                if any(x.get("upstream_splits") for x in sources.values())
                else "global-group-sha256-mod100-90/5/5-v1"
            ),
            "contamination_screen": (
                "exact payload + long-text 4-MinHash signature; "
                "no semantic contamination attestation"
                if near_screen == "minhash4"
                else "exact payload only here; upstream/public-benchmark screens recorded in "
                "source specification; no semantic contamination attestation"
            ),
            "qualification": "NOT_QUALIFIED",
        }
        write_json(temp / "manifest.json", manifest)
        temp.rename(destination)
        return digest(destination / "manifest.json")
    finally:
        for f in handles.values():
            f.close()
        con.close()
        if temp.exists():
            shutil.rmtree(temp)


class LanguageRelease:
    """Streaming reader whose split access is explicit; no implicit test loading."""

    def __init__(self, directory, manifest_sha256):
        self.directory = Path(directory)
        p = regular(self.directory, "manifest.json")
        if digest(p) != manifest_sha256:
            raise ForgeError("language manifest pin mismatch")
        self.manifest = json.loads(p.read_bytes())
        self.manifest_sha256 = manifest_sha256
        if self.manifest.get("schema") != "forge.language.v1":
            raise ForgeError("unsupported language release")
        self.verify()

    def verify(self):
        for name, item in self.manifest["files"].items():
            p = regular(self.directory, name)
            if (
                item["split"] not in SPLITS
                or item["kind"] not in KINDS
                or digest(p) != item["sha256"]
            ):
                raise ForgeError("language shard hash or contract mismatch")
        return True

    def iter_rows(self, split, kind):
        if split not in SPLITS or kind not in KINDS:
            raise ForgeError("explicit valid split and kind required")
        for name, item in sorted(self.manifest["files"].items()):
            if (item["split"], item["kind"]) == (split, kind):
                p = regular(self.directory, name)
                if digest(p) != item["sha256"]:
                    raise ForgeError("language shard changed")
                count = 0
                for row in rows(p):
                    payload(row)
                    count += 1
                    yield row
                if count != item["records"]:
                    raise ForgeError("language shard count mismatch")
