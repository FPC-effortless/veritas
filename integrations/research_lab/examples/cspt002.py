"""CSPT002: bounded, constructed-data objective-learning diagnostic.

No real-world capability, causal-identification or fair-architecture claim is
licensed by this file. All evaluated inputs are synthetic. PyTorch is optional
at repository install time; required only for the explicit manual fit.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

ENTITIES = tuple(f"e{i}" for i in range(12))
OBJECTS = tuple(f"o{i}" for i in range(8))
WORDS = ("<pad>", "<cls>", "first", "holds", "and", "then", "gives", "to",
         "query", "belongs", "while", "receives", "from", "now")
VOCAB = {word: i for i, word in enumerate((*WORDS, *ENTITIES, *OBJECTS))}
PAD = VOCAB["<pad>"]
ARMS = ("answer_only", "good_views", "completion", "causal_latent")


@dataclass(frozen=True)
class World:
    owners: tuple[int, int]
    objects: tuple[int, int]
    receiver: int
    moved_slot: int
    queried_slot: int

    def state_key(self) -> tuple[int, ...]:
        # Group all queries/paraphrases of the same underlying physical world.
        return (*self.owners, *self.objects, self.receiver, self.moved_slot)

    def canonical(self) -> tuple[int, ...]:
        return (*self.state_key(), self.queried_slot)

    def final_owners(self) -> tuple[int, int]:
        result = list(self.owners)
        result[self.moved_slot] = self.receiver
        return tuple(result)

    def answer(self) -> int:
        return self.final_owners()[self.queried_slot]

    def before_answer(self) -> int:
        return self.owners[self.queried_slot]

    def receiver_swap(self, *, same_split: bool = False) -> "World | None":
        # A counterfactual evaluation must also remain in the heldout split.
        candidates = [i for i in range(len(ENTITIES))
                      if i not in (*self.owners, self.receiver)]
        original_split = partition(self)
        for receiver in candidates:
            result = World(self.owners, self.objects, receiver,
                           self.moved_slot, self.queried_slot)
            if not same_split or partition(result) == original_split:
                return result
        return None

    def paired_role_swap(self) -> "World":
        return World(self.owners[::-1], self.objects,
                     self.receiver, self.moved_slot, self.queried_slot)


def partition(world: World) -> str:
    """Split by canonical semantics, not paraphrase or generated row index."""
    key = json.dumps(world.state_key(), separators=(",", ":")).encode()
    bucket = int(hashlib.sha256(key).hexdigest()[:12], 16) % 10
    return "train" if bucket < 8 else ("dev" if bucket == 8 else "test")


def sample_world(rng: random.Random, split: str) -> World:
    for _ in range(10000):
        e0, e1, receiver = rng.sample(range(len(ENTITIES)), 3)
        o0, o1 = rng.sample(range(len(OBJECTS)), 2)
        world = World((e0, e1), (o0, o1), receiver,
                      rng.randrange(2), rng.randrange(2))
        if partition(world) == split:
            return world
    raise RuntimeError("Could not sample semantic partition")


def render(world: World, view: int = 0, *, before_only: bool = False,
           target_only: bool = False) -> list[str]:
    e0, e1 = (ENTITIES[i] for i in world.owners)
    x, y = (OBJECTS[i] for i in world.objects)
    given = OBJECTS[world.objects[world.moved_slot]]
    sender = ENTITIES[world.owners[world.moved_slot]]
    receiver = ENTITIES[world.receiver]
    q = OBJECTS[world.objects[world.queried_slot]]
    if target_only:
        new0, new1 = (ENTITIES[i] for i in world.final_owners())
        return ["<cls>", "now", new0, "holds", x, "and", new1,
                "holds", y, "query", q]
    if view == 0:
        before = ["<cls>", "first", e0, "holds", x, "and", e1, "holds", y]
        action = ["then", sender, "gives", given, "to", receiver]
    else:
        before = ["<cls>", x, "belongs", e0, "while", y, "belongs", e1]
        action = ["then", receiver, "receives", given, "from", sender]
    return before + ([] if before_only else action) + ["query", q]


def tokens(words: list[str], max_len: int = 32) -> list[int]:
    if len(words) > max_len:
        raise ValueError(f"Truncated context would erase evidence: {len(words)}")
    result = [VOCAB[w] for w in words]
    return result + [PAD] * (max_len - len(result))


def batch_examples(worlds: list[World], device: str = "cpu"):
    import torch
    def tensor(view: int, **kw):
        return torch.tensor([tokens(render(w, view, **kw)) for w in worlds],
                            dtype=torch.long, device=device)
    return {
        "context": tensor(0),
        "paraphrase": tensor(1),
        "before": tensor(0, before_only=True),
        # Target text exists ONLY inside the training loss; never an inference input.
        "target_post": tensor(0, target_only=True),
        "owner": torch.tensor([w.answer() for w in worlds], device=device),
        "owner_before": torch.tensor([w.before_answer() for w in worlds], device=device),
    }


# Delay torch import until an actual model/test requests it.
def make_model(d: int = 48, layers: int = 2, heads: int = 4):
    import torch
    from torch import nn

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(len(VOCAB), d, padding_idx=PAD)
            self.position = nn.Embedding(32, d)
            block = nn.TransformerEncoderLayer(d, heads, 4*d, dropout=0.0,
                                               activation="gelu", batch_first=True,
                                               norm_first=True)
            self.backbone = nn.TransformerEncoder(block, layers, enable_nested_tensor=False)
            self.norm = nn.LayerNorm(d)

        def forward(self, input_ids):
            b, n = input_ids.shape
            if n > 32:
                raise ValueError("Context exceeds registered positional horizon")
            seq = self.embedding(input_ids) + self.position(
                torch.arange(n, device=input_ids.device))[None]
            mask = input_ids.eq(PAD)
            encoded = self.backbone(seq, src_key_padding_mask=mask)
            return self.norm(encoded[:, 0])

    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = Encoder()
            self.predictor = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d))
            self.answer = nn.Linear(d, len(ENTITIES))

        def forward(self, input_ids):
            representation = self.encoder(input_ids)
            return self.answer(self.predictor(representation)), representation

    return Model()


def count_parameters(model) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def evaluate(model, worlds: list[World], device: str = "cpu") -> dict[str, float]:
    """Evaluate true state binding, including untouched values and intervention.

    Each state contributes both item queries in its same heldout partition.
    The counterfactual receiver must also stay in the heldout partition.
    """
    import torch
    model.eval()
    right = 0
    affected_right = unaffected_right = 0
    affected = unaffected = 0
    two_query_joint = eligible = triplet_right = 0

    def predict(group: list[World]) -> list[int]:
        return model(batch_examples(group, device)["context"])[0].argmax(-1).tolist()

    with torch.no_grad():
        for offset in range(0, len(worlds), 96):
            group = worlds[offset:offset+96]
            for w, pred in zip(group, predict(group)):
                ok = int(pred == w.answer())
                right += ok
                if w.queried_slot == w.moved_slot:
                    affected += 1
                    affected_right += ok
                else:
                    unaffected += 1
                    unaffected_right += ok
            yes_worlds = [World(w.owners, w.objects, w.receiver,
                                w.moved_slot, w.moved_slot) for w in group]
            no_worlds = [World(w.owners, w.objects, w.receiver,
                               w.moved_slot, 1-w.moved_slot) for w in group]
            got_yes = predict(yes_worlds)
            got_no = predict(no_worlds)
            two_query_joint += sum(int(a == x.answer() and b == y.answer())
                                   for a, b, x, y in zip(got_yes, got_no,
                                                         yes_worlds, no_worlds))
            eligible_rows = []
            for i, w in enumerate(yes_worlds):
                alternate = w.receiver_swap(same_split=True)
                if alternate is not None:
                    eligible_rows.append((i, alternate))
            if eligible_rows:
                alternative_predictions = predict([w for _, w in eligible_rows])
                for (i, alternate), alt_prediction in zip(eligible_rows,
                                                            alternative_predictions):
                    eligible += 1
                    triplet_right += int(
                        got_yes[i] == yes_worlds[i].answer()
                        and got_no[i] == no_worlds[i].answer()
                        and alt_prediction == alternate.answer()
                        and got_yes[i] != alt_prediction
                    )
    return {"exact_owner": right / len(worlds),
            "affected_owner": affected_right / max(1, affected),
            "unaffected_owner": unaffected_right / max(1, unaffected),
            "two_query_joint": two_query_joint / len(worlds),
            "state_triplet_exact": triplet_right / max(1, eligible),
            "counterfactual_eligible": eligible,
            "counterfactual_coverage": eligible / len(worlds)}


def fit_arm(arm: str, seed: int, *, steps: int, batch_size: int,
            d: int = 48, layers: int = 2, lr: float = 0.002,
            device: str = "cpu", eval_size: int = 384):
    import torch
    from torch.nn import functional as F
    if arm not in ARMS:
        raise ValueError(arm)
    torch.manual_seed(seed)
    model = make_model(d=d, layers=layers).to(device)
    ema = copy.deepcopy(model.encoder).to(device)
    ema.eval()
    for p in ema.parameters():
        p.requires_grad_(False)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    rng = random.Random(10000 + seed)  # identical example stream for every arm
    dev_rng = random.Random(20000 + seed)
    test_rng = random.Random(30000 + seed)
    dev = [sample_world(dev_rng, "dev") for _ in range(eval_size)]
    test = [sample_world(test_rng, "test") for _ in range(eval_size)]
    train_hash = hashlib.sha256()
    start = time.perf_counter()
    loss_value = 0.0
    model.train()
    for step in range(steps):
        examples = [sample_world(rng, "train") for _ in range(batch_size)]
        for w in examples:
            train_hash.update(bytes(w.canonical()))
        b = batch_examples(examples, device)
        logits, z = model(b["context"])
        loss = F.cross_entropy(logits, b["owner"])
        if arm in ("good_views", "completion", "causal_latent"):
            z_alt = model.encoder(b["paraphrase"])
            loss = loss + 0.2 * (1.0 - F.cosine_similarity(z, z_alt).mean())
            # The supervised owner target anchors semantics; this regularizer
            # guards against view-only degeneracy without privileged labels.
            std = z.float().std(dim=0, unbiased=False)
            loss = loss + 0.01 * F.relu(0.2 - std).mean()
        if arm in ("completion", "causal_latent"):
            before, _ = model(b["before"])
            loss = loss + 0.5 * F.cross_entropy(before, b["owner_before"])
        if arm == "causal_latent":
            with torch.no_grad():
                target = ema(b["target_post"])
            prediction = model.predictor(z)
            loss = loss + 0.2 * (1.0 - F.cosine_similarity(prediction, target).mean())
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if arm == "causal_latent":
            with torch.no_grad():
                for p_ema, p_live in zip(ema.parameters(), model.encoder.parameters()):
                    p_ema.lerp_(p_live, 0.01)
        loss_value = float(loss.detach())
    elapsed = time.perf_counter() - start
    dev_results = evaluate(model, dev, device)
    test_results = evaluate(model, test, device)
    return model, {
        "study": "CSPT002", "arm": arm, "seed": seed,
        "source_kind": "CONSTRUCTED_SYNTHETIC_DIAGNOSTIC",
        "science_status": "NOT_QUALIFIED", "evaluation_status": "EXPLORATORY_UNSEALED",
        "steps": steps, "batch_size": batch_size, "train_scenarios_sha256": train_hash.hexdigest(),
        "instantiated_online_trainable_parameters": count_parameters(model),
        "ema_nontrainable_parameters": sum(p.numel() for p in ema.parameters()),
        "device": str(device), "seconds_training": elapsed,
        "final_train_loss": loss_value, "dev": dev_results, "test": test_results,
    }


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--seeds", nargs="+", type=int, default=[11, 23, 37])
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--d", type=int, default=48)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=0.002)
    parser.add_argument("--eval-size", type=int, default=384)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", type=Path, default=Path("cspt002-runs"))
    parser.add_argument("--save-checkpoints", action="store_true")
    args = parser.parse_args(argv)
    if min(args.steps, args.batch_size, args.d, args.layers, args.eval_size) < 1:
        parser.error("All positive integer experiment budgets must be nonzero")
    if args.d % 4:
        parser.error("--d must be divisible by four attention heads")
    import torch
    torch.set_num_threads(1)
    args.out.mkdir(parents=True, exist_ok=True)
    receipts = []
    for arm in args.arms:
        for seed in args.seeds:
            model, receipt = fit_arm(arm, seed, steps=args.steps,
                                     batch_size=args.batch_size, d=args.d,
                                     layers=args.layers, lr=args.lr,
                                     eval_size=args.eval_size, device=args.device)
            if args.save_checkpoints:
                torch.save({"model": model.state_dict(), "receipt": receipt,
                            "rng": torch.get_rng_state()}, args.out/f"{arm}-{seed}.pt")
            receipts.append(receipt)
            print(json.dumps({"arm": arm, "seed": seed,
                              "dev": receipt["dev"], "test": receipt["test"],
                              "seconds": round(receipt["seconds_training"], 2)},
                             sort_keys=True), flush=True)
    report = {"schema": "cspt002.exploratory_receipts.v1",
              "protocol": "CSPT002_SYNTHETIC_DIAGNOSTIC_ONLY",
              "args": {k: (str(v) if isinstance(v, Path) else v)
                       for k, v in vars(args).items()},
              "runs": receipts}
    (args.out/"results.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    run()
