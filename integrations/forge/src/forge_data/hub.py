"""Pinned public-Hub shard acquisition and bounded language preparation.

Raw shards stay in an external cache. Authentication is optional for public
sources and is obtained only from HF_TOKEN by the configured SDK. Receipts never
serialize credentials. Repository revisions and file SHA256s must be pinned.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from .core import ForgeError
from .language import MAX_ROW, LanguageRelease, build_release, canonical, digest, write_json


def object_hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_plan(path):
    plan = json.loads(Path(path).read_bytes())
    required = {
        "schema",
        "split_salt",
        "context",
        "vocab_size",
        "tokenizer_training_bytes",
        "pretrain_tokens",
        "evaluation_text_tokens",
        "quotas",
        "datasets",
    }
    if set(plan) != required or plan["schema"] != "forge.hub-plan.v1":
        raise ForgeError("unsupported acquisition plan fields")
    for key in (
        "context",
        "vocab_size",
        "tokenizer_training_bytes",
        "pretrain_tokens",
        "evaluation_text_tokens",
    ):
        if type(plan[key]) is not int or plan[key] < 1:
            raise ForgeError("positive acquisition budgets required")
    if plan["vocab_size"] < 264 or plan["context"] < 32:
        raise ForgeError("byte BPE vocabulary and conversation context too small")
    if set(plan["quotas"]) != {"conversation", "preference"}:
        raise ForgeError("conversation/preference quotas required")
    for counts in plan["quotas"].values():
        if set(counts) != {"train", "validation", "test"} or any(
            type(v) is not int or v < 1 for v in counts.values()
        ):
            raise ForgeError("positive quotas for every split required")
    names = set()
    for source in plan["datasets"]:
        if set(source) != {"name", "repo_id", "revision", "kind", "license", "provenance", "files"}:
            raise ForgeError("source must contain only pinned public source fields")
        if (
            not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", source["name"])
            or source["name"] in names
            or not re.fullmatch(r"[a-f0-9]{40}", source["revision"])
            or not source["license"]
            or not source["provenance"]
            or source["kind"] not in ("text", "conversation", "preference", "task")
        ):
            raise ForgeError("invalid source identity, revision or license")
        names.add(source["name"])
        for item in source["files"]:
            path = PurePosixPath(item["path"])
            if (
                set(item) != {"path", "size", "sha256", "upstream_split"}
                or path.is_absolute()
                or ".." in path.parts
                or not str(path).endswith(".parquet")
                or type(item["size"]) is not int
                or item["size"] <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
                or item["upstream_split"] not in ("train", "test")
            ):
                raise ForgeError("invalid pinned shard record")
            if (
                re.search(r"(?:^|[/_])test(?:[-_/]|$)", item["path"])
                and item["upstream_split"] != "test"
            ):
                raise ForgeError("a TEST-named shard cannot be declared TRAIN")

    if not names or len(names) != len(plan["datasets"]):
        raise ForgeError("nonempty unique sources required")
    return plan


@contextlib.contextmanager
def cache_lock(directory):
    import fcntl

    directory = Path(directory)
    if directory.is_symlink():
        raise ForgeError("symlink cache unsupported")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".prepare.lock").open("a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield directory


def _json_atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def _verified(path, item):
    return (
        path.is_file()
        and not path.is_symlink()
        and path.stat().st_size == item["size"]
        and digest(path) == item["sha256"]
    )


def acquire(plan_path, directory):
    """Fetch exactly reviewed shards; SDK cache supports interrupted downloads."""
    plan = read_plan(plan_path)
    root = Path(directory).resolve()
    with cache_lock(root):
        return _acquire(plan, root)


def _acquire(plan, root):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import hf_hub_download

    marker = root / "source-plan.json"
    if marker.exists() and object_hash(json.loads(marker.read_bytes())) != object_hash(plan):
        raise ForgeError("cache belongs to a different immutable source plan")
    _json_atomic(marker, plan)
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    work = [(source, item) for source in plan["datasets"] for item in source["files"]]

    def one(pair):
        source, item = pair
        target = root / "raw" / source["name"] / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _verified(target, item):
            if target.exists():
                raise ForgeError("cached shard hash mismatch; refusing silent replacement")
            print(f"Fetching {source['repo_id']} / {item['path']}", flush=True)
            downloaded = hf_hub_download(
                repo_id=source["repo_id"],
                repo_type="dataset",
                revision=source["revision"],
                filename=item["path"],
                cache_dir=root / "hf-cache",
                token=os.environ.get("HF_TOKEN") or False,
            )
            temporary = target.with_suffix(".download")
            temporary.unlink(missing_ok=True)
            # Same-filesystem hard links avoid keeping two full copies of multi-GB shards.
            try:
                os.link(Path(downloaded).resolve(), temporary)
            except OSError:
                shutil.copyfile(downloaded, temporary)
            if not _verified(temporary, item):
                temporary.unlink(missing_ok=True)
                raise ForgeError("downloaded shard size/SHA256 mismatch")
            temporary.replace(target)
        return {
            "source": source["name"],
            "repo_id": source["repo_id"],
            "revision": source["revision"],
            "upstream_split": item["upstream_split"],
            "file": str(target.relative_to(root)),
            "bytes": item["size"],
            "sha256": item["sha256"],
            "license": source["license"],
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(one, work))
    receipt = {
        "schema": "forge.hub-acquisition.v1",
        "plan_sha256": object_hash(plan),
        "files": files,
        "download_bytes": sum(x["bytes"] for x in files),
        "authentication": "optional HF_TOKEN, never serialized",
        "qualification": "NOT_QUALIFIED",
    }
    _json_atomic(root / "acquisition.json", receipt)
    return receipt


def parquet_rows(path):
    import pyarrow.parquet as pq

    for batch in pq.ParquetFile(path).iter_batches(batch_size=64):
        yield from batch.to_pylist()


def source_rows(plan, root, kind=None, upstream_split=None, *, skip_text=False):
    for source in plan["datasets"]:
        if skip_text and source["kind"] == "text":
            continue
        if kind and source["kind"] != kind:
            continue
        for item in source["files"]:
            if upstream_split and item["upstream_split"] != upstream_split:
                continue
            path = root / "raw" / source["name"] / item["path"]
            for row in parquet_rows(path):
                yield source, item["upstream_split"], row


def normalize_question(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


class HeldoutScreen:
    """Exact normalized question fingerprints, not semantic contamination proof."""

    def __init__(self, questions):
        import ahocorasick

        self.automaton = ahocorasick.Automaton()
        self.questions = set()
        for question in questions:
            normalized = normalize_question(question)
            self.questions.add(normalized)
            words = normalized.split()
            # Short questions use the whole question; longer ones use three 12-word windows.
            windows = (
                [normalized]
                if len(words) < 12
                else [
                    " ".join(words[p : p + 12])
                    for p in (0, (len(words) - 12) // 2, len(words) - 12)
                ]
            )
            for value in windows:
                self.automaton.add_word(" " + value + " ", 1)
        self.automaton.make_automaton()

    def contains(self, text):
        return next(self.automaton.iter(" " + normalize_question(text) + " "), None) is not None


def split_for(group, salt, upstream="train", *, text=False):
    if upstream == "test":
        return "test"
    value = int(hashlib.sha256((salt + "\0" + group).encode()).hexdigest()[:8], 16) % 100
    return (
        ("train" if value < 98 else "validation" if value == 98 else "test")
        if text
        else ("train" if value < 95 else "validation")
    )


def question_group(question):
    return "question:" + hashlib.sha256(normalize_question(question).encode()).hexdigest()


def clean_text(text):
    return (
        isinstance(text, str)
        and bool(text.strip())
        and len(text.encode()) < MAX_ROW // 2
        and not re.search(r"[\x00-\x08]", text)
        and "<|" not in text
    )


def public_prompt(source, row):
    """Identify public prompt groups before any context, score, or storage quotas."""
    if source["kind"] == "conversation":
        users = [
            m.get("content")
            for m in row.get("messages", [])
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        prompt = "\n".join(users) if users and all(isinstance(m, str) for m in users) else None
    elif source["kind"] == "preference":
        prompt = row.get("prompt")
    elif source["kind"] == "task":
        prompt = row.get("question")
    else:
        prompt = None
    return prompt if isinstance(prompt, str) and normalize_question(prompt) else None


def heldout_prompts(plan, root):
    """Reserve every official TEST group, including excluded or over-quota rows."""
    questions, official = [], set()
    for source, upstream, row in source_rows(plan, root, skip_text=True):
        prompt = public_prompt(source, row)
        if prompt is None:
            continue
        group = question_group(prompt)
        if upstream == "test":
            official.add(group)
        if split_for(group, plan["split_salt"], upstream) != "train":
            questions.append(prompt)
    return questions, official


def preparation_identity():
    from trainlab.fullcycle import tokenization

    return object_hash(
        {
            name: digest(path)
            for name, path in {
                "hub": Path(__file__),
                "language": Path(__file__).with_name("language.py"),
                "verifiers": Path(__file__).with_name("verifiers.py"),
                "tokenization": Path(tokenization.__file__),
            }.items()
        }
    )


def text_examples(plan, root, screen, rejects=None):
    for source, upstream, row in source_rows(plan, root, "text"):
        text = row.get("text")
        if not clean_text(text) or screen.contains(text):
            if rejects is not None:
                rejects["text_control_or_public_eval_overlap"] += 1
            continue
        url = row.get("url") or row.get("id")
        if not isinstance(url, str) or not url:
            if rejects is not None:
                rejects["missing_document_identity"] += 1
            continue
        if "://" in url:
            parsed = urlsplit(url)
            url = urlunsplit(
                (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
            )
        group = "document:" + hashlib.sha256(url.encode()).hexdigest()
        yield {
            "kind": "text",
            "source_id": source["name"],
            "group": group,
            "split": split_for(group, plan["split_salt"], upstream, text=True),
            "upstream_split": upstream,
            "text": text,
        }


def prepare(plan_path, directory):
    """Download, screen, fit TRAIN BPE, enforce lengths, then freeze a release."""
    plan = read_plan(plan_path)
    with cache_lock(Path(directory).resolve()) as root:
        acquisition = _acquire(plan, root)
        prepared = root / "prepared.json"
        if prepared.exists():
            result = json.loads(prepared.read_bytes())
            if (
                result["plan_sha256"] != object_hash(plan)
                or digest(root / result["tokenizer"]["path"]) != result["tokenizer"]["sha256"]
                or result.get("preparation_identity") != preparation_identity()
            ):
                raise ForgeError("prepared cache identity mismatch")
            LanguageRelease(root / "release", result["manifest_sha256"])
            return result
        return _prepare(plan, root, acquisition)


def _prepare(plan, root, acquisition):
    import sqlite3

    from trainlab.fullcycle.tokenization import Tokens, fit_tokenizer

    from .language import payload
    from .verifiers import extract_gsm8k_answer

    # Includes ALL official TEST plus TRAIN-derived validation prompts across sources.
    heldout, official_test_groups = heldout_prompts(plan, root)
    if not heldout:
        raise ForgeError("public math held-out screen cannot be empty")
    screen = HeldoutScreen(heldout)
    screen_sha256 = object_hash(sorted(screen.questions))

    class TrainTexts:
        def iter_rows(self, split, kind):
            if split != "train":
                raise ForgeError("tokenizer may only consume TRAIN")
            if kind != "text":
                return
            for row in text_examples(plan, root, screen):
                if row["split"] == "train":
                    yield row

    tokenizer_path = root / "tokenizer.json"
    fit_receipt = root / "tokenizer-training.json"
    if fit_receipt.exists():
        record = json.loads(fit_receipt.read_bytes())
        if (
            record["plan_sha256"] != object_hash(plan)
            or record["sha256"] != digest(tokenizer_path)
            or record.get("screen_sha256") != screen_sha256
            or record.get("preparation_identity") != preparation_identity()
        ):
            raise ForgeError("tokenizer training identity changed")
    else:
        print("Fitting BPE exclusively on screened TRAIN text", flush=True)
        temporary = root / "tokenizer-fitting.json"
        fit_tokenizer(
            TrainTexts(),
            temporary,
            kind="bpe",
            vocab_size=plan["vocab_size"],
            max_training_bytes=plan["tokenizer_training_bytes"],
        )
        temporary.replace(tokenizer_path)
        _json_atomic(
            fit_receipt,
            {
                "plan_sha256": object_hash(plan),
                "split": "train",
                "max_training_bytes": plan["tokenizer_training_bytes"],
                "public_heldout_prompts_screened": len(screen.questions),
                "screen_sha256": screen_sha256,
                "preparation_identity": preparation_identity(),
                "sha256": digest(tokenizer_path),
            },
        )
    tokens = Tokens(tokenizer_path)
    if tokens.vocab_size != plan["vocab_size"]:
        raise ForgeError("insufficient TRAIN sample to fit the exact requested vocabulary")
    source_path = root / "normalized.jsonl"
    counts, rejected, text_tokens = Counter(), Counter(), Counter()
    scratch = tempfile.TemporaryDirectory(prefix=".prepare-index-", dir=root)
    db = sqlite3.connect(Path(scratch.name) / "index.sqlite")
    db.executescript(
        "CREATE TABLE seen (digest TEXT PRIMARY KEY);"
        "CREATE TABLE groups (name TEXT PRIMARY KEY, split TEXT);"
    )
    db.executemany(
        "INSERT INTO groups VALUES (?, 'test')",
        ((group,) for group in sorted(official_test_groups)),
    )
    try:
        with source_path.open("wb") as output:

            def emit(row):
                # Resolve exact upstream TEST collisions before writing any TRAIN use.
                previous = db.execute(
                    "SELECT split FROM groups WHERE name=?", (row["group"],)
                ).fetchone()
                if previous and previous[0] != row["split"]:
                    rejected["cross_split_group_collision"] += 1
                    return False
                key = object_hash(payload(row))
                try:
                    db.execute("INSERT INTO seen VALUES (?)", (key,))
                except sqlite3.IntegrityError:
                    rejected["exact_duplicate_payload"] += 1
                    return False
                db.execute(
                    "INSERT OR IGNORE INTO groups VALUES (?,?)", (row["group"], row["split"])
                )
                line = canonical(row) + b"\n"
                if len(line) > MAX_ROW:
                    raise ForgeError("normalization emitted an oversized record")
                output.write(line)
                counts[row["split"] + "/" + row["kind"]] += 1
                return True

            for row in text_examples(plan, root, screen, rejected):
                split = row["split"]
                goal = (
                    plan["pretrain_tokens"] if split == "train" else plan["evaluation_text_tokens"]
                )
                if text_tokens[split] >= goal:
                    if all(
                        text_tokens[s]
                        >= (
                            plan["pretrain_tokens"]
                            if s == "train"
                            else plan["evaluation_text_tokens"]
                        )
                        for s in ("train", "validation", "test")
                    ):
                        break
                    continue
                n = len(tokens.encode(row["text"])) + 1
                if emit(row):
                    text_tokens[split] += n
                if counts["train/text"] % 10000 == 0 and split == "train":
                    print(f"Prepared {text_tokens['train']:,} unique TRAIN text tokens", flush=True)
            for split in ("train", "validation", "test"):
                goal = (
                    plan["pretrain_tokens"] if split == "train" else plan["evaluation_text_tokens"]
                )
                if text_tokens[split] < goal:
                    raise ForgeError(
                        f"selected shards cannot meet the declared {split} token budget"
                    )

            # Official TEST is processed first so later exact prompt overlap cannot enter TRAIN.
            for requested in ("test", "train"):
                for source, upstream, raw in source_rows(
                    plan, root, upstream_split=requested, skip_text=True
                ):
                    kind = source["kind"]
                    if kind == "text":
                        continue
                    name = source["name"]
                    if kind == "conversation":
                        # The source card assigns Apache-2.0 to this generated component.
                        if raw.get("source") != "smol-magpie-ultra-short":
                            rejected["smoltalk_other_component"] += 1
                            continue
                        messages = [
                            {"role": m.get("role"), "content": m.get("content")}
                            for m in raw.get("messages", [])
                        ]
                        if (
                            not messages
                            or messages[-1]["role"] != "assistant"
                            or any(
                                m["role"] not in ("user", "assistant", "system", "tool")
                                or not clean_text(m["content"])
                                for m in messages
                            )
                        ):
                            rejected["invalid_conversation"] += 1
                            continue
                        prompt = "\n".join(m["content"] for m in messages if m["role"] == "user")
                        group = question_group(prompt)
                        split = split_for(group, plan["split_salt"], upstream)
                        quota = plan["quotas"]["conversation"][split]
                        if counts[split + "/smoltalk_conversation"] >= quota:
                            continue
                        if split == "train" and screen.contains(
                            " ".join(m["content"] for m in messages)
                        ):
                            rejected["public_eval_question_in_conversation"] += 1
                            continue
                        if len(tokens.conversation(messages)[0]) > plan["context"] + 1:
                            rejected["over_context_conversation"] += 1
                            continue
                        if emit(
                            {
                                "kind": "conversation",
                                "source_id": name,
                                "group": group,
                                "split": split,
                                "upstream_split": upstream,
                                "messages": messages,
                            }
                        ):
                            counts[split + "/smoltalk_conversation"] += 1
                    elif kind == "preference":
                        prompt, chosen, denied = (
                            raw.get("prompt"),
                            raw.get("chosen"),
                            raw.get("rejected"),
                        )
                        if (
                            not clean_text(prompt)
                            or not isinstance(chosen, list)
                            or not isinstance(denied, list)
                            or len(chosen) != 2
                            or len(denied) != 2
                            or chosen[0] != denied[0]
                            or chosen[0] != {"role": "user", "content": prompt}
                            or chosen[-1].get("role") != "assistant"
                            or denied[-1].get("role") != "assistant"
                        ):
                            rejected["unsupported_preference_shape"] += 1
                            continue
                        a, b = chosen[-1]["content"], denied[-1]["content"]
                        score_a, score_b = raw.get("score_chosen"), raw.get("score_rejected")
                        if (
                            not clean_text(a)
                            or not clean_text(b)
                            or a == b
                            or not isinstance(score_a, (int, float))
                            or not isinstance(score_b, (int, float))
                            or not score_a > score_b
                        ):
                            rejected["preference_tie_or_invalid"] += 1
                            continue
                        group = question_group(prompt)
                        split = split_for(group, plan["split_salt"], upstream)
                        if counts[split + "/preference"] >= plan["quotas"]["preference"][split]:
                            continue
                        if split == "train" and screen.contains(prompt + " " + a + " " + b):
                            rejected["public_eval_question_in_preference"] += 1
                            continue
                        if any(
                            len(tokens.preference(prompt, answer)[0]) > plan["context"] + 1
                            for answer in (a, b)
                        ):
                            rejected["over_context_preference"] += 1
                            continue
                        emit(
                            {
                                "kind": "preference",
                                "source_id": name,
                                "group": group,
                                "split": split,
                                "upstream_split": upstream,
                                "prompt": prompt,
                                "chosen": a,
                                "rejected": b,
                            }
                        )
                    elif kind == "task":
                        question, solution = raw["question"], raw["answer"]
                        answer = extract_gsm8k_answer(solution)
                        if not clean_text(question) or not clean_text(solution) or answer is None:
                            raise ForgeError("invalid original GSM8K problem/solution")
                        group = question_group(question)
                        split = split_for(group, plan["split_salt"], upstream)
                        if split == "train" and screen.contains(question):
                            rejected["gsm8k_train_overlap_heldout"] += 1
                            continue
                        prompt = (
                            question
                            + "\nSolve the problem. Finish with #### followed by the answer."
                        )
                        if (
                            len(
                                tokens.conversation(
                                    [{"role": "user", "content": prompt}], prompt=True
                                )[0]
                            )
                            > plan["context"] - 128
                        ):
                            rejected["over_context_rl_prompt"] += 1
                            continue
                        emit(
                            {
                                "kind": "task",
                                "source_id": name,
                                "group": group,
                                "split": split,
                                "upstream_split": upstream,
                                "prompt": prompt,
                                "expected_answer": answer,
                                "verifier": "gsm8k-exact-v1",
                            }
                        )
                        messages = [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": solution},
                        ]
                        if len(tokens.conversation(messages)[0]) <= plan["context"] + 1:
                            emit(
                                {
                                    "kind": "conversation",
                                    "source_id": name,
                                    "group": group,
                                    "split": split,
                                    "upstream_split": upstream,
                                    "messages": messages,
                                }
                            )
                        else:
                            rejected["over_context_math_sft"] += 1
        for kind in ("conversation", "preference"):
            for split, quota in plan["quotas"][kind].items():
                key = split + (
                    "/smoltalk_conversation" if kind == "conversation" else "/preference"
                )
                if counts[key] < quota:
                    raise ForgeError(
                        f"curated {key} count {counts[key]} is below declared quota {quota}"
                    )
        sources = {
            s["name"]: {
                "rights_reviewed": True,
                "license": s["license"],
                "provenance": s["provenance"],
                "source_kind": "AUTHENTIC_CANDIDATE",
                "repo_id": s["repo_id"],
                "revision": s["revision"],
                "generation": "public synthetic/model-judged"
                if s["kind"] in ("conversation", "preference")
                else "public web corpus"
                if s["kind"] == "text"
                else "public math problems",
                "upstream_splits": {
                    "train": ["train", "validation", "test"]
                    if s["kind"] == "text"
                    else ["train", "validation"],
                    "test": ["test"],
                },
            }
            for s in plan["datasets"]
        }
        spec = {
            "schema": "forge.language-source.v1",
            "source_sha256": digest(source_path),
            "split_salt": plan["split_salt"],
            "sources": sources,
            "near_dedupe": "exact-only",
            "acquisition_sha256": digest(root / "acquisition.json"),
            "public_question_screen": {
                "questions": len(screen.questions),
                "screen_sha256": screen_sha256,
                "official_test_groups_reserved": len(official_test_groups),
                "method": "normalized 12-word "
                "first/middle/last fingerprints; no semantic contamination attestation",
            },
            "preparation_rejected": dict(rejected),
            "preparation_counts": dict(counts),
            "preparation_identity": preparation_identity(),
        }
        _json_atomic(root / "source-spec.json", spec)
        release_dir = root / "release"
        if release_dir.exists():
            existing = json.loads((release_dir / "manifest.json").read_bytes())
            if existing["source_spec"] != spec:
                raise ForgeError("existing release differs from prepared source")
            pin = digest(release_dir / "manifest.json")
        else:
            print("Freezing source-group and upstream split boundaries", flush=True)
            pin = build_release(source_path, spec, release_dir)
        result = {
            "schema": "forge.hub-prepared.v1",
            "plan_sha256": object_hash(plan),
            "preparation_identity": preparation_identity(),
            "manifest_sha256": pin,
            "release": "release",
            "tokenizer": {"path": "tokenizer.json", "sha256": digest(tokenizer_path)},
            "training_text_tokens_before_pack": dict(text_tokens),
            "counts": dict(counts),
            "rejected": dict(rejected),
            "acquisition_sha256": digest(root / "acquisition.json"),
            "qualification": "NOT_QUALIFIED",
        }
        _json_atomic(root / "prepared.json", result)
        return result
    finally:
        db.close()
        scratch.cleanup()
