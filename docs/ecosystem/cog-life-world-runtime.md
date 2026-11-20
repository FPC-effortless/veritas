# COG-LIFE native constructed world runtime

This is the host-side world for an 081 engineering diagnostic, not a learned runtime, accelerator, real-world simulation certification or benchmark promotion. It makes no network or external calls. It journals and re-executes synthetic actions only.

## Native initialization and isolation

`LifeWorld.from_world_factory(seed)` uses the actual WorldFactory and validates the resulting CanonicalWorld. The eight local actors and three local places bind to canonical person/address IDs, and their initial locations derive from the as-of residence relations and creating events. The developmental clock and placed objects are local synthetic behavior, not civil facts or canonical legal ages. `LifeWorld(seed)` is a lighter isolated mechanism fixture, with no canonical-world lineage; do not give it credit for native lineage. The E0 bridge rejects the lightweight variant.

Only serialize `dataclasses.asdict(observation)` into a candidate input, per actor and up to the cutoff. Do not give candidate code a live world, port closure, native identity, generator seeds, adjudication log, checkpoint, or evaluator reference. The AgentPort is a cooperative API, not security isolation against Python reflection. Per-actor sequence and opaque IDs don't change merely because another agent received a hidden event. Visible parents must already be visible to that observer; a missing citation is not evidence of independence. Location-scope inspection and denied action receipts intentionally reveal limited local consequences and should be charged in any policy comparison.

## Commands, replay, and custody

- `advance(tick)` advances deterministically, with autonomous placement, testimony, promises, requests and movement. Childhood is the initial stage; ticks 12 and 24 generate the adolescent/adult milestones.
- `port(actor).act(Action(...))` checks local actor/source/evidence scopes. Place requires ownership, local access and the currently observed object version. Same actor/request ID and exact contents replay without a second state change; conflicting keys fail. Evidence IDs from another agent cannot be used. Only explicitly synthetic host fixtures can register local reversible-response probe controls.
- `inject` is privileged local fixture input with separately scoped visibility, never a real-world authority action. It cannot impersonate native actor/source or reserved core event type. This API does not verify the semantic correctness of experiment-specific payloads.
- `event_log()`, `truth()`, `native_identity()`, `save`, `load`, and `fork` are host/evaluator only. Save is a same-filesystem atomic replacement file; this is not a product-grade crash, distributed transaction or authentication guarantee. History is reversible by forking an immutable prefix, not editing the old track. Restore replays the synthetic tick algorithm, checked actions and expressly trusted fixture commands and checks exact content. Pin trusted complete checkpoint bytes externally if replacement is in risk scope; an unkeyed in-file hash chain alone cannot authenticate a completely replaced, consistently regenerated track.
- `native_bridge.life_experience(world, actor)` re-executes the host log then exports the native TrajectoryV2 observer trace and MachineExperience E0_TRACEABLE. It is evaluator-private, with deterministic-replay diagnostic metadata and no competence reward. It cannot be put into a public export. Candidate datasets should be constructed separately from the permitted actor views, not by handing them these evidence objects.

## Mechanical check

From a verified native installation (including its already approved existing dependency closure), run `PYTHONPATH=src:<verified vendor path> python tests/test_life_world.py`. These are deterministic unit tests for world/authority/visibility/replay, not a fit or held split. Eight passed at the initial implementation. A separate native TrainLab stage and independent reviewer are required for scoped experimental evidence.
