"""Build public fullcycle datasets; constructed post-training is labeled as such.

Download Tiny Shakespeare separately or pass an existing input.txt. This script
records the exact acquired bytes and uses disjoint non-overlapping source chunks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forge_data.language import build_release, canonical, digest, write_json


def prepare(text_path, output, *, steps_scale=1.0):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "source.jsonl"
    with source.open("wb") as f:

        def emit(row):
            f.write(canonical(row) + b"\n")

        with Path(text_path).open(encoding="utf-8") as text:
            i = 0
            while block := text.read(8192):
                emit(
                    {
                        "kind": "text",
                        "source_id": "tinyshakespeare",
                        "group": f"shakespeare-nonoverlap-chunk-{i}",
                        "text": block,
                    }
                )
                i += 1
        for left in range(20):
            for right in range(20):
                prompt = f"Compare integers: {left}, {right}. Answer 0 if first is larger, else 1."
                chosen = "0" if left > right else "1"
                group = f"comparison-operands-{left}-{right}"
                base = {"source_id": "constructed-comparison", "group": group}
                emit(
                    {
                        **base,
                        "kind": "task",
                        "prompt": prompt,
                        "left": left,
                        "right": right,
                        "verifier": "integer-comparison-v1",
                    }
                )
                emit(
                    {
                        **base,
                        "kind": "preference",
                        "prompt": prompt,
                        "chosen": chosen,
                        "rejected": "1" if chosen == "0" else "0",
                    }
                )
                emit(
                    {
                        **base,
                        "kind": "conversation",
                        "messages": [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": chosen},
                        ],
                    }
                )
        qa = [
            ("What does Forge do?", "Forge prepares versioned training datasets."),
            ("What does TrainLab do?", "TrainLab runs training stages and saves checkpoints."),
            ("What does Veritas do?", "Veritas evaluates capabilities and checks evidence."),
            ("What is a checkpoint?", "A checkpoint saves model weights and training state."),
            ("What is pretraining?", "Pretraining learns patterns from text."),
            ("What is supervised fine tuning?", "It trains a model on example responses."),
            ("What is a tokenizer?", "A tokenizer converts text into token IDs."),
            (
                "Why use held out data?",
                "It measures performance on examples excluded from training.",
            ),
            (
                "What is DPO?",
                "DPO trains a model to prefer chosen responses over rejected responses.",
            ),
            (
                "What is reinforcement learning?",
                "A policy learns from rewards for its sampled actions.",
            ),
            (
                "Are you a large assistant?",
                "No. I am a small research model with limited training.",
            ),
            ("What is a gradient?", "A gradient indicates how a parameter affects the loss."),
        ]
        for i, (question, answer) in enumerate(qa):
            for prefix in ("", "Please answer: ", "In one sentence: ", "Help me understand: "):
                emit(
                    {
                        "kind": "conversation",
                        "source_id": "constructed-chat",
                        "group": f"qa-concept-{i}",
                        "messages": [
                            {"role": "user", "content": prefix + question},
                            {"role": "assistant", "content": answer},
                        ],
                    }
                )
        for word in (
            "lamp",
            "chair",
            "table",
            "river",
            "forest",
            "sun",
            "moon",
            "orange",
            "green",
            "blue",
            "paper",
            "pencil",
            "book",
            "window",
            "cloud",
            "rain",
            "stone",
            "grass",
            "field",
            "garden",
            "bread",
            "water",
            "silver",
            "gold",
        ):
            for command in ("Say exactly: ", "Repeat this word: ", "Return only: "):
                emit(
                    {
                        "kind": "conversation",
                        "source_id": "constructed-chat",
                        "group": "copy-word-" + word,
                        "messages": [
                            {"role": "user", "content": command + word},
                            {"role": "assistant", "content": word},
                        ],
                    }
                )
        for value in range(40):
            emit(
                {
                    "kind": "conversation",
                    "source_id": "constructed-chat",
                    "group": f"tool-value-{value}",
                    "messages": [
                        {"role": "user", "content": f"Calculate {value} plus 1."},
                        {"role": "assistant", "content": f"calculator({value}+1)"},
                        {"role": "tool", "content": str(value + 1)},
                        {"role": "assistant", "content": str(value + 1)},
                    ],
                }
            )
    spec = {
        "schema": "forge.language-source.v1",
        "source_sha256": digest(source),
        "split_salt": "fullcycle-public-fixture-001",
        "sources": {
            "tinyshakespeare": {
                "rights_reviewed": True,
                "license": "public-domain-Shakespeare-text",
                "provenance": "https://github.com/karpathy/char-rnn/blob/master/"
                "data/tinyshakespeare/input.txt",
                "source_kind": "AUTHENTIC_CANDIDATE",
                "acquired_file_sha256": digest(text_path),
                "split_scope": "non-overlap chunks of one public corpus; not author/play-disjoint",
            },
            "constructed-chat": {
                "rights_reviewed": True,
                "license": "Apache-2.0",
                "provenance": "FULLCYCLE-001 prepare_demo.py",
                "source_kind": "CONSTRUCTED",
            },
            "constructed-comparison": {
                "rights_reviewed": True,
                "license": "Apache-2.0",
                "provenance": "FULLCYCLE-001 prepare_demo.py",
                "source_kind": "CONSTRUCTED",
            },
        },
    }
    write_json(output / "source-spec.json", spec)
    pin = build_release(source, spec, output / "release")
    stages = [
        dict(name=name, steps=max(1, int(steps * steps_scale)), batch_size=batch, learning_rate=lr)
        for name, steps, batch, lr in [
            ("pretrain", 300, 8, 0.001),
            ("midtrain", 40, 8, 0.0005),
            ("sft", 160, 8, 0.0003),
            ("dpo", 40, 8, 0.0002),
            ("rl", 40, 4, 0.0001),
        ]
    ]
    for stage in stages:
        if stage["name"] != "pretrain":
            stage["replay_weight"] = 0.5
    for backend in ("transformer", "tac098"):
        config = {
            "schema": "trainlab.pipeline.v1",
            "seed": 7,
            "device": "cpu",
            "cpu_threads": 2,
            "precision": "fp32",
            "deterministic": True,
            "checkpoint_every": 25,
            "evaluation_token_budget": 2048,
            "dataset": {"directory": "release", "manifest_sha256": pin},
            "tokenizer": {"kind": "bpe" if backend == "transformer" else "byte", "vocab_size": 512},
            "model": {
                "backend": backend,
                "width": 144 if backend == "transformer" else 32,
                "layers": 4 if backend == "transformer" else 1,
                "heads": 4 if backend == "transformer" else 1,
                "context": 256,
                "activation_checkpointing": False,
            },
            "stages": stages,
        }
        write_json(output / f"{backend}.json", config)
    write_json(
        output / "DATA_CARD.json",
        {
            "corpus": "Tiny Shakespeare, author William Shakespeare (1564–1616)",
            "source_bytes_sha256": digest(text_path),
            "release_sha256": pin,
            "posttraining": "constructed educational chat and integer comparison examples",
            "rights_scope": "operator-reviewed public-domain text; not legal attestation",
            "contamination_limit": "same corpus and task grammar across group-disjoint splits",
            "no_external_generalization_claim": True,
        },
    )
    return {"directory": str(output), "manifest_sha256": pin}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--steps-scale", type=float, default=1.0)
    args = parser.parse_args()
    print(json.dumps(prepare(args.text, args.output, steps_scale=args.steps_scale), indent=2))
