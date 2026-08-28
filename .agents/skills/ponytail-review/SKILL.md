---
name: ponytail-review
description: Review a diff exclusively for removable over-engineering and unnecessary complexity; applies no fixes.
---
# ponytail-review
Run only the complexity axis, separate from correctness/security/performance. One finding per line when possible: `<file>:L<line>: <tag> <what to cut>. <replacement>.`

Tags: `delete` dead/speculative/unused flexibility; `stdlib` hand-rolled standard-library behavior; `native` code/dependency replaced by platform capability; `yagni` premature abstraction/config/layer; `shrink` same behavior materially more directly.

A minimal smoke/regression check is not bloat. End with `net: -<N> lines possible` only as a forward-looking cut estimate, never a claim of measured historical savings. If nothing material is cuttable: `Lean already. Ship.` Report only; do not apply fixes unless separately authorized.
