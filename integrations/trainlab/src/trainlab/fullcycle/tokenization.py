"""Train-only byte BPE plus the exact 256-byte vocabulary needed by TAC098."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from trainlab.runner import LabError, digest, write_json

SPECIAL = [
    "<|pad|>",
    "<|bos|>",
    "<|eos|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|tool|>",
    "<|end|>",
]


class Tokens:
    def __init__(self, path):
        self.path = Path(path)
        config = json.loads(self.path.read_bytes())
        self.byte = config.get("kind") == "byte-v1"
        if self.byte:
            self.tokenizer = None
            self.vocab_size = 256
            self.special = {s: i for i, s in enumerate(SPECIAL)}
        else:
            from tokenizers import Tokenizer

            self.tokenizer = Tokenizer.from_file(str(path))
            self.vocab_size = self.tokenizer.get_vocab_size()
            self.special = {s: self.tokenizer.token_to_id(s) for s in SPECIAL}
        self.pad, self.bos, self.eos = (self.special[s] for s in SPECIAL[:3])
        self.end = self.special[SPECIAL[-1]]
        if any(v is None for v in self.special.values()):
            raise LabError("tokenizer control tokens missing")

    def encode(self, text):
        if any(s in text for s in SPECIAL):
            raise LabError("literal tokenizer control tokens in content")
        if self.byte:
            value = list(text.encode("utf-8"))
            if any(t < 8 for t in value):
                raise LabError("reserved control byte in text")
            return value
        return self.tokenizer.encode(text, add_special_tokens=False).ids

    def decode(self, ids):
        if self.byte:
            return bytes(int(t) for t in ids if int(t) >= 8).decode("utf-8", errors="replace")
        return self.tokenizer.decode([int(i) for i in ids], skip_special_tokens=True)

    def conversation(self, messages, *, prompt=False):
        ids, mask = [self.bos], [False]
        for message in messages:
            role = message["role"]
            if role not in ("system", "user", "assistant", "tool"):
                raise LabError("invalid chat role")
            part = [self.special[f"<|{role}|>"]] + self.encode(message["content"]) + [self.end]
            ids += part
            mask += [False] + [role == "assistant"] * (len(part) - 1)
        if prompt:
            ids += [self.special["<|assistant|>"]]
            mask += [False]
        return ids, mask

    def preference(self, prompt, answer):
        ids, mask = self.conversation([{"role": "user", "content": prompt}], prompt=True)
        target = self.encode(answer) + [self.end]
        return ids + target, mask + [True] * len(target)


def fit_tokenizer(
    release,
    output,
    *,
    kind="bpe",
    vocab_size=512,
    max_training_bytes=8 * 1024 * 1024,
    artifact_path=None,
    artifact_sha256=None,
):
    output = Path(output)
    if kind == "artifact":
        import shutil

        artifact = Path(artifact_path)
        if digest(artifact) != artifact_sha256:
            raise LabError("prepared tokenizer artifact hash mismatch")
        Tokens(artifact)
        if artifact.resolve() != output.resolve():
            shutil.copyfile(artifact, output)
    elif kind == "byte":
        write_json(
            output,
            {
                "kind": "byte-v1",
                "control_tokens": SPECIAL,
                "training_split": "train",
                "vocab_size": 256,
            },
        )
    elif kind == "bpe":
        from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

        tok = Tokenizer(models.BPE())
        tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tok.decoder = decoders.ByteLevel()
        trainer = trainers.BpeTrainer(
            vocab_size=vocab_size,
            special_tokens=SPECIAL,
            initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
            show_progress=False,
            min_frequency=2,
        )

        def texts():
            remaining = max_training_bytes
            if type(remaining) is not int or remaining < 256:
                raise LabError("tokenizer training byte budget must be at least 256")
            for kind in ("text", "conversation"):
                for row in release.iter_rows("train", kind):
                    values = (
                        [row["text"]]
                        if kind == "text"
                        else [message["content"] for message in row["messages"]]
                    )
                    for value in values:
                        if remaining <= 0:
                            return
                        value = value.encode("utf-8")[:remaining].decode("utf-8", errors="ignore")
                        remaining -= len(value.encode("utf-8"))
                        yield value

        tok.train_from_iterator(texts(), trainer=trainer)
        tok.save(str(output))
    else:
        raise LabError("tokenizer must be bpe, byte or a pinned artifact")
    return digest(output)


def pack_training(release, tokens, directory):
    """Tokenize bounded rows into append-only raw uint32 streams; never load TEST."""
    directory = Path(directory)
    directory.mkdir(exist_ok=True)
    info = {}
    for split in ("train", "validation"):
        path = directory / f"{split}.bin"
        size = 0
        with path.open("wb") as f:
            for row in release.iter_rows(split, "text"):
                ids = tokens.encode(row["text"]) + [tokens.eos]
                np.asarray(ids, dtype="<u4").tofile(f)
                size += len(ids)
        if not size:
            raise LabError(f"no {split} text tokens")
        info[split] = {"path": path.name, "tokens": size, "sha256": digest(path)}
    for kind in ("conversation", "preference", "task"):
        path = directory / f"train-{kind}.jsonl"
        offsets_path = directory / f"train-{kind}.offsets"
        count = 0
        with path.open("wb") as f, offsets_path.open("wb") as index:
            for row in release.iter_rows("train", kind):
                value = tokens.conversation(row["messages"]) if kind == "conversation" else row
                np.asarray([f.tell()], dtype="<u8").tofile(index)
                f.write(json.dumps(value, separators=(",", ":")).encode() + b"\n")
                count += 1
        for p in (path, offsets_path):
            info[p.name] = {"path": p.name, "records": count, "sha256": digest(p)}
    write_json(directory / "manifest.json", info)
    return info


class RecordSource:
    """Disk-backed random access to tokenized TRAIN rows, bounded per-record RAM."""

    def __init__(self, directory, kind, *, all_tokens=False):
        self.path = Path(directory) / f"train-{kind}.jsonl"
        index = Path(directory) / f"train-{kind}.offsets"
        self.count = index.stat().st_size // 8
        self.offsets = np.memmap(index, mode="r", dtype="<u8") if self.count else []
        self.all_tokens = all_tokens

    def __len__(self):
        return self.count

    def __getitem__(self, i):
        if not 0 <= i < self.count:
            raise IndexError(i)
        with self.path.open("rb") as f:
            f.seek(int(self.offsets[i]))
            value = json.loads(f.readline(1024 * 1024 + 1))
        if self.all_tokens:
            value[1] = [True] * len(value[0])
        return value
