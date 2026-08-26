from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from investigation_world.foundry.models import DistributionSplit, FoundryTaskMetadata, stable_hash


class DistributionPartition(BaseModel):
    split: DistributionSplit
    task_ids: list[str] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    generator_parameters: dict = Field(default_factory=dict)


class FoundryDistributionManifest(BaseModel):
    manifest_id: str
    version: str
    partitions: list[DistributionPartition]

    @model_validator(mode="after")
    def validate_disjoint(self):
        seen_tasks: set[str] = set()
        seen_seeds: dict[int, DistributionSplit] = {}
        seen_splits: set[DistributionSplit] = set()
        for partition in self.partitions:
            if partition.split in seen_splits:
                raise ValueError(f"duplicate split: {partition.split}")
            seen_splits.add(partition.split)
            overlap = seen_tasks.intersection(partition.task_ids)
            if overlap:
                raise ValueError(f"task IDs cross split boundary: {sorted(overlap)[:3]}")
            seen_tasks.update(partition.task_ids)
            for seed in partition.seeds:
                if seed in seen_seeds:
                    raise ValueError(f"seed {seed} shared by {seen_seeds[seed]} and {partition.split}")
                seen_seeds[seed] = partition.split
        return self

    @property
    def content_hash(self) -> str:
        return stable_hash(self.model_dump(mode="json", exclude={"manifest_id"}))


def manifest_from_tasks(tasks: list[FoundryTaskMetadata], *, version: str = "1") -> FoundryDistributionManifest:
    partitions = []
    for split in DistributionSplit:
        members = sorted((item for item in tasks if item.split == split), key=lambda item: item.task_id)
        if members:
            partitions.append(DistributionPartition(
                split=split,
                task_ids=[item.task_id for item in members],
                seeds=[item.seed for item in members],
            ))
    digest = stable_hash([version, [part.model_dump(mode="json") for part in partitions]])[:16].upper()
    return FoundryDistributionManifest(manifest_id=f"FDM-{digest}", version=version, partitions=partitions)
