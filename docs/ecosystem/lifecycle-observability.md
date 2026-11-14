# Lifecycle absence observability

`investigation_world.benchmark.lifecycle_observability` provides a bounded,
development-only counterfactual diagnostic for controlled COPY/LINK pairs.
It does not dispatch models or alter campaign admission or coverage thresholds.

A final-map example containing `DELETE source; SET source new` may test only
overwrite behavior. To test the absence interval, some scored consequence must
change when deletion is removed. `audit_pair(left, right, stratum)` identifies
the unique focal COPY/LINK contrast and replaces every nonempty subset of later
source DELETEs with NOP. It reports full-map and composed-probe sensitivity
separately. Joint ablations catch redundant deletes that mask individual effects.

The diagnostic also distinguishes transient absence snapshots from directly
preserved snapshots. A COPY must traverse the focal destination's live path,
terminate at the missing source, and resolve a concrete value under ablation.
For direct preservation, its destination must have no later write and must remain
UNKNOWN at its own final query, while the ablated answer differs. Cycles and
other missing roots do not qualify. This deliberately conservative criterion can
miss absence preserved indirectly through later operations.
The focal destination must retain its original COPY/LINK binding; later writes
to it are rejected so replacement edges cannot masquerade as the focal contrast.

Inputs use `woyengi.lifecycle.v1`: string keys/values, typed null for UNKNOWN,
SET, DELETE, COPY, LINK and NOP. A failed COPY removes its previous destination;
self-copy resolves before changing that destination. Full-map queries include
every declared key. Bounds: 64 keys, 256 events and four audited source DELETEs
(at most 15 interventions per row). Invalid or uncontrolled pairs raise errors.

For a retrospective ecosystem run, freeze the existing Forge TRAIN/validation
release and source/runtime hashes, use an ordinary TrainLab diagnostic recipe,
independently verify baseline and ablated maps with a backward-history oracle,
and record a private Veritas evidence envelope plus Research Lab provenance.
Keep prior failed coverage and model admission status. Do not route an
underpowered dataset through the model-campaign adapter as a passing campaign.

This diagnostic is not a complete causal-template quotient. Changed final
answers do not establish independent components, learned binding, lower cost,
or scientific qualification. Repetitions, renamed payloads and workload depth
remain correlated development examples; confidence intervals must respect that.

Targeted verification:

```sh
python -m pytest tests/unit/test_lifecycle_observability.py
python -O -m unittest discover -s tests/unit -p test_lifecycle_observability.py
```
