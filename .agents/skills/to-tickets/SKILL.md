---
name: to-tickets
description: Split an approved spec into dependency-aware minimal vertical slices suitable for fresh agent contexts.
---
# to-tickets
Each ticket must define outcome, prerequisites, owned files/surfaces, non-goals, falsifier/tests, evidence, verification, and authority constraints. Prefer observable vertical slices and the fewest tickets/files that preserve independent ownership and review. Tickets should reuse/delete/native/stdlib before creating new components, and must not add “future” scaffolding not required by the approved outcome. If parallel agents are active, assign non-overlapping file ownership explicitly. Separate implementation-complete tickets from qualification/evidence tickets when they require different workflows.
