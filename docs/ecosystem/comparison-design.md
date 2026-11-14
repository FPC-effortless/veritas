# Compare paired outcomes across evaluation units and training seeds

Use `freeze_design` to declare the complete comparison family, unit and seed
identities, context and analysis window hashes, selection mode, alpha, draw
count, and random seed before analysis. Retain the returned design hash
separately. Supply the exact context hash to `analyze` alongside the plan and
observations. The required cells are the Cartesian product of comparison,
unit and seed. Use the evaluation sampling unit, such as a base scenario or
subject, when multiple examples share that unit.

Each observation has `comparison`, `unit`, `seed`, `status`, `candidate`, and
`baseline`. Mark observed pairs `OBSERVED` and give two finite scores. A
declared `FAILED` or `MISSING` cell has null scores. Omitted cells appear as
missing. Duplicate or out-of-plan observations are rejected. Formula and
sampling assumptions apply to comparable raw scores for a declared metric.

The complete-panel estimate is the equal-cell mean of paired differences.
With a fixed declared design and sufficient coverage and tail resolution,
the analysis draws unit levels and seed levels separately with replacement.
Each draw includes their crossed cells with multiplicity. Candidate and
baseline stay paired within every cell. All comparison members share the
same drawn levels. Unit-only and seed-only resampling summarize the
sensitivity to each axis while holding the other fixed. The main crossed
interval uses Bonferroni-adjusted percentile endpoints across the declared
family. The two single-axis intervals are supporting descriptions.

When any member has missing or failed cells, the family intervals are
withheld. The observed-cell mean remains descriptive and can differ from the
complete-panel effect. A single unit or seed, insufficient bootstrap draws
in an adjusted tail, and adaptive or unknown selection also withhold
intervals. The tool does not supply sequential testing or post-selection
correction. Independent exchangeability and freezing before exposure are
declared properties. Correlated groups, correlated seed draws and few
levels can make percentile intervals unreliable. A narrow interval on an
invariant panel does not validate inference outside it.
