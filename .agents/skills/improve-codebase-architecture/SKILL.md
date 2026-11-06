---
name: improve-codebase-architecture
description: Find high-leverage architectural improvements and removable complexity without mixing them into unrelated behavior changes.
---
# improve-codebase-architecture
Inspect dependency structure, hotspots, duplicated invariants, leaky interfaces, oversized composition roots, and unstable tests. Add a repo-wide Ponytail audit: dependencies duplicating stdlib/native capabilities, single-implementation interfaces, one-product factories, delegate-only wrappers, semantically empty layers/files, dead flags/config, and hand-rolled stdlib. Rank largest credible cuts first, with replacement and approximate cut size when defensible. Score structural proposals by leverage, semantic risk, migration cost, and testability. Keep complexity-only findings distinct from correctness/security/performance defects. For Veritas preserve public/private oracle separation, verifier independence, deterministic replay, and qualification boundaries. Turn material refactors into separate specs/tickets rather than opportunistic rewrites.
