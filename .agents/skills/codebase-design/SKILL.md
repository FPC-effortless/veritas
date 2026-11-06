---
name: codebase-design
description: Design deep modules and stable seams while refusing premature abstractions and needless layers.
---
# codebase-design
Evaluate interface cost versus complexity hidden. Prefer stable ports/adapters, narrow composition roots, localized invariants, and public seams testable without internal knowledge. Keep policy separate from mechanism. Apply the minimality ladder before inventing a new boundary: no interface for one implementation, factory for one product, config for a value that does not vary, wrapper that only delegates, or new dependency when stdlib/native/already-installed capability suffices. Real abstractions are justified when they hide substantial complexity, enforce invariants, or support demonstrated multiplicity—not merely future possibility. In Veritas preserve verifier independence, public/private separation, deterministic reconstruction/replay promises, and versioned environment contracts.
