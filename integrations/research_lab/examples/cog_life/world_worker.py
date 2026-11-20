"""081 engineering worker. No fitted model, held truth, or external actions."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from importlib import import_module

ROOT = Path(__file__).resolve().parent
# Match the model exports needed by the exact native experience adapter.
# This is a bounded native source slice, not whole-product import assurance.
def native_import_slice():
    for name, folder in (("investigation_world", ROOT / "investigation_world"),
                         ("investigation_world.trajectory", ROOT / "investigation_world/trajectory")):
        if name in sys.modules or not folder.is_dir():
            raise ValueError("native slice must start fresh from staged bundle")
        module = ModuleType(name)
        module.__path__ = [str(folder)]
        sys.modules[name] = module
    actual = import_module("investigation_world.trajectory.models")
    public = sys.modules["investigation_world.trajectory"]
    for name in ("TrajectoryV2", "FailureCategory", "VisibilityClass", "canonical_hash"):
        setattr(public, name, getattr(actual, name))

native_import_slice()
from investigation_world.life import Action, LifeWorld, PEOPLE, LOCATIONS
from investigation_world.life.native_bridge import life_experience

def track(w):
    return {actor: [asdict(row) for row in w.port(actor).observe()] for actor in PEOPLE}

def check(seed: int):
    a = LifeWorld.from_world_factory(seed)
    b = LifeWorld.from_world_factory(seed)
    identity = a.native_identity()
    if (len(set(identity["person_ids"].values())) != 8
            or len(set(identity["location_ids"].values())) != 3
            or len(identity["residence_witnesses"]) != 8):
        raise ValueError("unbound canonical person/place or initial provenance")
    a.advance(8)
    b.advance(8)
    for w in (a, b):
        w.register_probe("bench", {"cue": {"signal": 1}}, allowed=("p0",))
        if w.port("p1").act(Action("probe", "bench", "cue")).authorized:
            raise ValueError("denied role acquired probe")
        r = w.port("p0").act(Action("probe", "bench", "cue", request_id="once"))
        if not (r.authorized and r.applied):
            raise ValueError("eligible local probe failed")
        denied = w.port("p2").act(Action("testify", "p3", "bear", (r.observation_id,)))
        if denied.authorized or denied.applied:
            raise ValueError("foreign evidence citation crossed scope")
    if a.event_log() != b.event_log():
        raise ValueError("identical early program diverged")
    with TemporaryDirectory() as tmp:
        checkpoint = Path(tmp) / "state.json"
        b.save(checkpoint)
        b = LifeWorld.load(checkpoint)
    n = len(b.event_log())
    retry = b.port("p0").act(Action("probe", "bench", "cue", request_id="once"))
    if not retry.replayed or retry.cost != 0 or len(b.event_log()) != n:
        raise ValueError("retry produced duplicate workload/state transition")
    # Invisible private insertion may not affect another actor's local sequence or IDs.
    aa, bb = a.fork(len(a.event_log())), b.fork(len(b.event_log()))
    bb.inject("private_marker", {"dummy": 1}, ("p1",))
    for w in (aa, bb):
        w.inject("seen", {"dummy": 0}, ("p0",))
    if aa.port("p0").observe() != bb.port("p0").observe():
        raise ValueError("hidden event disturbed public chronology")
    for w in (a, b):
        w.advance(30)
        if w.stage != "adult":
            raise ValueError("milestones not reached")
    log = a.event_log()
    if not (log == b.event_log() and a.truth() == b.truth() and track(a) == track(b)):
        raise ValueError("resumed forward trajectory not identical")
    native = LifeWorld.replay(log)
    if not (native.event_log() == log and track(native) == track(a)):
        raise ValueError("replay parsed but did not re-execute exact actor observations")
    for actor in PEOPLE:
        seen = set()
        for row in a.port(actor).observe():
            if not set(row.parents) <= seen or row.id in seen:
                raise ValueError("local provenance has future parent or repeated identity")
            seen.add(row.id)
    exp_a, exp_b = life_experience(a, "p0"), life_experience(b, "p0")
    if (exp_a.model_dump(mode="json") != exp_b.model_dump(mode="json")
            or exp_a.trajectory.original_evaluation.reward != 0
            or exp_a.trajectory.world.world_id != identity["world_id"]
            or len(exp_a.trajectory.events) != len(a.port("p0").observe())):
        raise ValueError("native evidence is not an exact private observer trace")
    return {"event_count": len(log), "actor_count": len(PEOPLE), "location_count": len(LOCATIONS),
            "cold_replay_exact": True, "hidden_insert_invariant": True, "denied_cases": 2,
            "replayed_without_write": 1}


def main():
    if sys.argv[1:] != ["world-check"]:
        raise ValueError("unexpected purpose")
    spec = json.loads((ROOT / "world-spec.json").read_text(encoding="utf-8"))
    if set(spec) != {"schema", "role", "seeds"} or spec["schema"] != "coglife.world-check.v1" or spec["role"] != "ENGINEERING_DESIGN":
        raise ValueError("unexpected input role")
    seeds = spec["seeds"]
    if (not isinstance(seeds, list) or not 3 <= len(seeds) <= 12
            or any(type(s) is not int or not 0 <= s < 2**63 for s in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError("expected distinct bounded engineering seeds")
    bits = [check(seed) for seed in seeds]
    out = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    with (out / "world-check.json").open("x", encoding="utf-8") as stream:
        json.dump({"scope": "ENGINEERING_DESIGN_ONLY", "lifetimes": len(bits),
                   "transitions": sum(b["event_count"] for b in bits),
                   "cold_replays_exact": len(bits), "actors_per_life": len(PEOPLE),
                   "locations_per_life": len(LOCATIONS), "denied_negative_cases": 2 * len(bits),
                   "once_only_retries": len(bits), "native_canonical_worlds": len(bits),
                   "native_e0_experiences": len(bits), "no_held_or_fit": True}, stream, sort_keys=True)
    (out / "metrics.json").write_text(json.dumps({"lifetimes": len(bits)}), encoding="utf-8")


if __name__ == "__main__":
    main()
