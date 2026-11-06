# Installing the Universal Coding Agent System in another repository

Copy:
- `.agents/universal/CONTRACT.md`
- `.agents/universal/PONYTAIL-FUSION.md`
- `.agents/skills/`
- `docs/agents/universal-workflow.md`
- `docs/agents/verification.md`

Add an `AGENTS.md` that places repository-specific instructions, security constraints, issue/spec requirements, and local overlays above the universal contract.

The skill pack currently preserves the 25 adapted Matt Pocock compatibility names plus six Ponytail compatibility skills. Keep both upstream MIT notices (`LICENSE-MATT-POCOCK` and `LICENSE-PONYTAIL`).

Do not make the universal layer the highest authority. Local safety, privacy, data, scientific, release, and branch-ownership rules must override it.

For repositories with specialized semantics, create `.agents/<repo-or-domain>/OVERLAY.md` rather than forking the universal contract. Apply Ponytail minimality through the universal contract so every local skill inherits it consistently rather than copying the ladder into every file.
