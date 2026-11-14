"""Exercise pinned SlotStore SET state through the Veritas diagnostic adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from trainlab.prediction_artifacts import (
    conformance_checks,
    make_request,
    read_predictions,
    write_predictions,
)
from trainlab.research_diagnostics import Diagnostic, Workbench
from trainlab.runner import LabError, digest, write_json
from trainlab.state_diagnostics import lifecycle, restore_isolation
from trainlab.token_memory_adapter import TokenMemory

PINS = {
    "native_slot.py": "48df5c75d2a4da1e5a1f39b028f4bdc793e15d4a71a58e9261484d3410f86992",
    "slot_101.pt": "45c7f6d6760c1ef0dde9c3d34f308fd24e177840bb9068dacbebdb2ed589272a",
}
DRIVER_PIN = "37cce07139ab28dda071c1b6805532194edd1d396c8cecec52a70c73593de51f"


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main(source, root):
    import io
    import sys
    from importlib.util import module_from_spec, spec_from_file_location

    import torch

    driver_file = (
        Path(__file__).resolve().parents[2] / "research_lab/examples/changing_state_replay.py"
    )
    paths = {source / name: pin for name, pin in PINS.items()}
    paths[driver_file] = DRIVER_PIN
    byte_sources = {}
    for path, pin in paths.items():
        if not path.is_file() or path.is_symlink():
            raise LabError("native source must be a regular file")
        with path.open("rb") as stream:
            payload = stream.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024 or hashlib.sha256(payload).hexdigest() != pin:
            raise LabError("native replay source/checkpoint identity differs")
        byte_sources[path.name] = payload
    # Both imports use verified source snapshots in a fresh private directory.
    with TemporaryDirectory(prefix="veritas-native-model-") as temp:
        driver_snapshot = Path(temp) / "driver.py"
        driver_snapshot.write_bytes(byte_sources[driver_file.name])
        spec = spec_from_file_location("veritas_replay_encoder", driver_snapshot)
        if spec is None or spec.loader is None:
            raise LabError("could not bind replay driver")
        driver = module_from_spec(spec)
        spec.loader.exec_module(driver)
        verified_source = Path(temp) / "native_slot.py"
        verified_source.write_bytes(byte_sources["native_slot.py"])
        module = driver.load_module(verified_source, "veritas_accepted_slot")
    torch.set_num_threads(1)
    torch.manual_seed(101)
    weights = torch.load(
        io.BytesIO(byte_sources["slot_101.pt"]), map_location="cpu", weights_only=True
    )["model"]
    keys = [f"r{i}" for i in range(4)]
    initial = [{"op": "set", "key": k, "value": f"v{i}"} for i, k in enumerate(keys)]
    edits = [{"op": "set", "key": "r0", "value": "v6"}, {"op": "set", "key": "r2", "value": "v7"}]
    peer_edit = {"op": "set", "key": "r1", "value": "v5"}

    def original(events, key):
        return driver.encode({"keys": keys, "events": events}, key)

    def token_event(event):
        return {"op": "tokens", "tokens": original([event], keys[0])[1:-7]}

    def expected(events):
        return {r["key"]: r["value"] for r in events}

    def make_native():
        model = module.SlotStore()
        model.load_state_dict(weights)
        model.eval()
        before = {name: value.detach().clone() for name, value in model.state_dict().items()}

        def init():
            with torch.inference_mode():
                state = model.init_state(1, "cpu")
                _, state = model.step(torch.tensor([driver.VOCAB["<bos>"]]), state)
                return state

        def run(tokens, state):
            with torch.inference_mode():
                for token in tokens:
                    logits, state = model.step(torch.tensor([token]), state)
                if not torch.isfinite(logits).all():
                    raise LabError("native model emitted nonfinite logits")
                return driver.TOKENS[int(logits.argmax(-1).item())], state

        def unchanged():
            return all(
                torch.equal(value, before[name]) for name, value in model.state_dict().items()
            )

        return TokenMemory(
            init,
            run,
            identity=sha(PINS),
            vocabulary_size=len(driver.TOKENS),
            clone_state=lambda state: tuple(t.detach().clone() for t in state),
        ), unchanged

    native, source_unchanged = make_native()
    peer, peer_unchanged = make_native()
    queries = [{"id": key, "input": original([], key)[1:]} for key in keys]
    rows = []
    for events in (initial, initial + edits):
        for key in keys:
            query = original([], key)[1:]
            history = [token_event(event)["tokens"] for event in events]
            flat = [driver.VOCAB["<bos>"]] + [i for block in history for i in block] + query
            if flat != original(events, key):
                raise LabError("adapter token boundaries differ from original encoder")
            rows.append(
                {"id": f"{len(events)}:{key}", "input": {"history": history, "query": query}}
            )
    steps = [
        {
            "id": f"overwrite-{i}",
            "event": token_event(edit),
            "expected": expected(initial + edits[: i + 1]),
            "touched": [edit["key"]],
        }
        for i, edit in enumerate(edits)
    ]
    identities = {
        "model": PINS["slot_101.pt"],
        "code": digest(Path(__file__)),
        "dataset": sha([initial, edits, peer_edit]),
        "configuration": sha([PINS, DRIVER_PIN, rows, "CPU FP32 one thread"]),
    }
    reports, predictions = {}, {}
    root.mkdir(parents=True, exist_ok=False)
    reports_path = root / "lifecycle.json"

    def observe(ctx):
        reports["lifecycle"] = lifecycle(
            ctx,
            initial=[token_event(e) for e in initial],
            initial_expected=expected(initial),
            queries=queries,
            steps=steps,
            supported_ops=["tokens"],
        )
        reports["restore"] = restore_isolation(
            ctx,
            initial=[token_event(e) for e in initial],
            queries=queries,
            expected=expected(initial),
            mutation=token_event(edits[0]),
            mutated_expected=expected(initial + edits[:1]),
            peer_mutation=token_event(peer_edit),
            peer_mutated_expected=expected(initial + [peer_edit]),
        )
        statuses = {report["status"] for report in reports.values()}
        status = (
            "FAILED"
            if "FAILED" in statuses
            else ("TESTED" if statuses == {"TESTED"} else "INCONCLUSIVE")
        )
        write_json(reports_path, reports)
        return {
            "status": status,
            "summary": "Native SET lifecycle and behavioral restore isolation.",
            "metrics": {"checked_reports": len(reports)},
        }

    def score_rows(ctx):
        request = make_request(
            identities,
            rows,
            task={"name": "native-slot-set", "output_schema": "finite-json-v1"},
            state={
                "mode": "stateless",
                "initial_state_sha256": sha([PINS, DRIVER_PIN, driver.VOCAB["<bos>"]]),
                "persists": "within each row history",
                "query_mutates": False,
                "reset": "fresh native state per row",
            },
        )
        actual = ctx.invoke("predict_rows", deepcopy(rows), phase="answer")
        path = root / "predictions.json"
        pin = write_predictions(path, request, actual)
        saved = read_predictions(path, pin, request)
        expected_rows = [expected(events)[k] for events in (initial, initial + edits) for k in keys]
        count = sum(a["output"] == b for a, b in zip(saved, expected_rows, strict=True))
        predictions.update(correct=count, queries=len(rows), sha256=pin)
        return {
            "status": "TESTED" if count == len(rows) else "FAILED",
            "summary": "Exact stored-output recount against SET reference.",
            "metrics": {"correct": count, "queries": len(rows)},
        }

    checks = [
        Diagnostic(
            "native_lifecycle",
            "1",
            ("update", "query", "restore", "peer_restore"),
            observe,
            "SET and independent restored peer",
        ),
        *conformance_checks(rows, mode="stateless"),
        Diagnostic(
            "bound_predictions",
            "1",
            ("predict_rows",),
            score_rows,
            "ordered fresh replay and exact output recount",
        ),
    ]
    result = Workbench(
        native.as_adapter("slotstore", peer=peer),
        identities,
        root / "workbench",
        max_calls=256,
        max_seconds=45,
    ).run(checks)
    unchanged = source_unchanged() and peer_unchanged()
    summary = {
        "checkpoint": PINS,
        "encoder_sha256": DRIVER_PIN,
        "seed": 101,
        "training": "NOT_RUN",
        "runtime": {
            "python": sys.version,
            "torch": str(torch.__version__),
            "machine": platform.machine(),
            "device": "cpu",
            "threads": 1,
        },
        "inputs": {"initial": initial, "edits": edits, "peer_edit": peer_edit, "rows": rows},
        "predictions": predictions,
        "weights_unchanged": unchanged,
        "coverage": result["coverage"],
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "summary.json", summary)
    if not unchanged or any(c["status"] != "TESTED" for c in result["coverage"]):
        raise LabError("native diagnostic acceptance failed; inspect retained evidence")
    print(json.dumps({"path": str(root), "checks": len(result["coverage"]), **predictions}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    main(args.source.resolve(), args.root.resolve())
