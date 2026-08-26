# ProjectWorld Procedural Construction Distribution

ProjectWorld's first production distribution is a versioned long-horizon construction environment family. It deliberately does not mutate the legacy five-domain `OperationalEpisode` distribution in place.

## Default size

`ProjectDistributionConfig()` compiles 896 projects:

| Split | Projects |
|---|---:|
| train | 512 |
| IID test | 128 |
| OOD | 128 |
| adversarial | 128 |
| **total** | **896** |

Each project is a complete design-to-handover environment rather than a single short operational task.

## What is procedurally generated

The generator begins from the validated construction project grammar and deterministically parameterizes it from a private generation seed.

Public project variation includes:

- building archetype;
- number of storeys;
- floorplate and gross floor area;
- project delivery model;
- site/logistics profile;
- construction market index;
- work-package direct costs;
- work-package durations;
- labor/material quantities;
- resource unit prices;
- procurement lead times;
- design-option downstream effects;
- project budget;
- project deadline.

Private ground-truth variation includes:

- permit/work-package delays;
- additional execution delays;
- procurement delays;
- latent quality defects;
- rework costs;
- rework durations;
- compound disruption pressure.

All variation is deterministic for a fixed distribution seed.

## Split semantics

### Train

Train projects use the normal construction operating envelope:

- mixed-use;
- residential;
- office;
- hotel;
- ordinary/suburban/constrained urban sites.

They provide broad scale, cost, schedule, procurement, role-authority, design-choice, and quality-control variation.

### IID test

IID cases draw from the same project archetype support as training but use disjoint seeds and held-out combinations.

### OOD

OOD projects introduce project and site regimes absent from training:

- hospitals;
- laboratories;
- data centers;
- educational facilities;
- brownfield sites;
- coastal sites;
- remote sites;
- dense CBD sites;
- low-rise and very high-rise scale extremes.

The goal is to test whether a project-delivery policy transfers the learned operational structure rather than memorizing a building template.

### Adversarial

Adversarial projects combine:

- tighter budget contingency;
- tighter schedule contingency;
- volatile market pricing;
- constrained site conditions;
- multiple work-package delays;
- multiple procurement delays;
- at least three latent defects.

The adversarial split therefore attacks long-horizon planning and recovery, not just language robustness.

## Public/private boundary

Agent-facing bundles contain only:

```text
public manifest
+ public project specifications
```

They do not contain:

```text
split identity
seed
scenario family
surface profile
oracle
latent defects
hidden delays
compound-disruption flags
```

Evaluator bundles retain those fields plus the exact private `ProjectOracle`.

The public and private bundle hashes are generated separately so benchmark packaging can verify that public material remains fixed while evaluator truth stays sequestered.

## Why this is separate from the legacy OperationalEpisode distribution

The existing production distribution and ProjectWorld differ at two levels.

First, the legacy distribution is already a versioned measurement instrument. Changing a benchmark's domain set, case count, support, or verifier semantics under the same version breaks longitudinal comparability.

Second, ProjectWorld is not currently another `OperationalEpisode`. It has a different environment contract:

```text
OperationalEpisode
  short/medium operational task
  action-effect oracle
  seven-dimensional operational verifier

ProjectScenario
  long-horizon persistent project
  event queue + resources + procurement
  role authority + decisions + inspections
  latent disruptions + rework
  project outcome verifier
```

Forcing ProjectWorld into `WorldDomain` before defining a compatibility adapter would make the enum claim that all domains share one runtime/verifier contract when they do not.

The intended evolution is therefore versioned composition:

```text
Veritas 0.8 legacy operational distribution
            +
ProjectWorld Construction Distribution v1
            ↓
new canonical Veritas distribution/version
```

A future canonical version can expose both under one manifest once the Foundry/Observatory adapters and cross-environment distribution contract are implemented. At that point adding ProjectWorld to the canonical benchmark is desirable; silently rewriting an older benchmark is not.
