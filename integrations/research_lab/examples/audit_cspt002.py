"""Read-only exact checkpoint replay of CSPT002 constructed diagnostic."""
import argparse
import hashlib
import json
import random
from pathlib import Path

import cspt002 as c
import torch


def audit(paths, *, arms=None):
    torch.set_num_threads(1)
    records = []
    for path in sorted(paths):
        obj = torch.load(path, map_location="cpu", weights_only=True)
        receipt = obj["receipt"]
        if arms and receipt["arm"] not in arms:
            continue
        assert receipt["study"] == "CSPT002"
        assert receipt["science_status"] == "NOT_QUALIFIED"
        assert receipt["source_kind"] == "CONSTRUCTED_SYNTHETIC_DIAGNOSTIC"
        assert receipt["steps"] == 120 and receipt["batch_size"] == 32
        model = c.make_model()
        model.load_state_dict(obj["model"], strict=True)
        model.eval()
        assert c.count_parameters(model) == receipt["instantiated_online_trainable_parameters"]
        for split, seed_offset in (("dev", 20000), ("test", 30000)):
            rng = random.Random(seed_offset+receipt["seed"])
            worlds = [c.sample_world(rng, split) for _ in range(384)]
            replayed = c.evaluate(model, worlds)
            for key, value in replayed.items():
                if abs(value - receipt[split][key]) > 1e-12:
                    raise AssertionError(
                        f"{path} {split} {key} mismatch {value} != {receipt[split][key]}"
                    )
        records.append({
            **receipt,
            "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checkpoint_filename": path.name,
            "exact_dev_test_replay": "PASS",
        })
    return records


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--paths", nargs="+", type=Path, required=True)
    p.add_argument("--arms", nargs="+", choices=c.ARMS)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    records = audit(args.paths, arms=args.arms)
    args.output.write_text(json.dumps(records, indent=2)+"\n")
    print(json.dumps({"replayed": len(records), "arms": sorted(set(x["arm"] for x in records)),
                      "all_passed": True}))
