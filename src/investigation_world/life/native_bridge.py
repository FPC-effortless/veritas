"""Bind life initialization to a validated native WorldFactory and export E0 evidence.

The full CanonicalWorld and evaluator identity never enter the candidate view.
The synthetic stage clock is not a person's legal age or an authentic timeline.
"""
from dataclasses import asdict
from investigation_world.core.models import Predicate
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig
from investigation_world.trajectory.models import (
    AgentIdentity, ArtifactIdentity, EvaluationRecord, ProvenanceRecord, RuntimeIdentity,
    StateDigest, StateDigestScope, TaskIdentity, TerminationRecord, TrajectoryEvent,
    TrajectoryReference, TrajectoryV2, VerifierIdentity, VisibilityClass, WorldIdentity,
)
from investigation_world.experience.adapter import machine_experience_from_trajectory
from investigation_world.experience.models import MachineExperience
from .models import PEOPLE, LOCATIONS
from .runtime import LifeWorld, SCHEMA, hash_obj

def canonical_seed(seed):
    config=WorldGenerationConfig(num_people=8,num_addresses=3,num_organizations=2)
    world=WorldFactory.generate(seed,config)
    world.validate()
    people=dict(zip(PEOPLE, sorted(world.people), strict=True))
    places=dict(zip(LOCATIONS, sorted(world.addresses), strict=True))
    names={v:k for k,v in places.items()}
    current=world.relationships_at(config.timeline_start)
    locs={};witnesses={}
    for alias,canonical_person in people.items():
        resident=[r for r in current if r.subject_id==canonical_person and r.predicate==Predicate.RESIDES_AT]
        if len(resident)!=1 or resident[0].object_id not in names or not resident[0].created_by_event_id:
            raise ValueError("canonical initial residence missing required scope/provenance")
        locs[alias]=names[resident[0].object_id]
        witnesses[alias]=resident[0].created_by_event_id
    return {
        "world_id":world.world_id,"world_digest":hash_obj(world.model_dump(mode="json")),
        "generator_version":world.metadata["generator_version"],
        "anchor":config.timeline_start.isoformat(),"person_ids":people,"location_ids":places,
        "initial_locations":locs,"residence_witnesses":witnesses,
    }

def life_trajectory(world: LifeWorld, observer: str, *, task_id="cog-life-081-replay") -> TrajectoryV2:
    """Evaluator-only native trace of the observer's exact visible event history."""
    events=world.event_log()
    restored=LifeWorld.replay(events)
    source_id=restored.native_identity()
    if restored.truth()!=world.truth():
        raise ValueError("world and replay disagree")
    rows=restored.port(observer).observe()
    vis=VisibilityClass.EVALUATOR_PRIVATE
    v=VerifierIdentity(verifier_id="cog-life-world-replay",version="1")
    initial=StateDigest(digest=hash_obj({"scope":"life visible prefix"}),scope=StateDigestScope.SEMANTIC)
    previous=initial;chain=[]
    for r in rows:
        before=previous
        previous=StateDigest(digest=hash_obj([before.digest,asdict(r)]),scope=StateDigestScope.SEMANTIC)
        chain.append(TrajectoryEvent(
            step=r.seq,event_type=r.kind,payload=asdict(r),state_before=before,state_after=previous,
            observation_references=(TrajectoryReference(reference_id=r.id,reference_type="life_visible_record",visibility=vis),),
            evidence_references=tuple(TrajectoryReference(reference_id=p,reference_type="life_visible_parent",visibility=vis)
                                      for p in r.parents),visibility=vis))
    return TrajectoryV2(
        world=WorldIdentity(environment_id="cog-life", environment_version="1",
             world_id=source_id["world_id"],world_version=source_id["generator_version"],
             world_bundle=ArtifactIdentity(artifact_id=source_id["world_id"],contract="canonical-world-factory",
                     version=source_id["generator_version"],digest=source_id["world_digest"],visibility=vis)),
        task=TaskIdentity(task_id=task_id),agent=AgentIdentity(agent_id=observer),
        runtime=RuntimeIdentity(runtime_id=SCHEMA,version="1"),verifier=v,initial_state=initial,
        events=tuple(chain),original_evaluation=EvaluationRecord(verifier=v,
                  component_scores={"deterministic_replay":1.0},reward=0.0),
        termination=TerminationRecord(reason="retained_prefix",terminated=False,truncated=False),
        final_state=previous,provenance=(ProvenanceRecord(source_kind="constructed",
             source_id=source_id["world_id"],source_version=SCHEMA,source_digest=events[-1]["digest"],
             adapter_id="cog-life-observer-trace",adapter_version="1",visibility=vis),),visibility=vis)

def life_experience(world: LifeWorld, observer: str, *, task_id="cog-life-081-replay") -> MachineExperience:
    """E0 traceability only; native canonical identity and readiness checks apply."""
    e=machine_experience_from_trajectory(life_trajectory(world,observer,task_id=task_id))
    return MachineExperience.model_validate({**e.model_dump(mode="python"),"visibility":VisibilityClass.EVALUATOR_PRIVATE})
