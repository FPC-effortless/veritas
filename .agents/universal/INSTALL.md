# Installing the Universal Coding Agent System in another repository

Copy:
- `.agents/universal/CONTRACT.md`
- `.agents/skills/`
- `docs/agents/universal-workflow.md`
- `docs/agents/verification.md`

Add an `AGENTS.md` that places repository-specific instructions, security constraints, issue/spec requirements, and local overlays above the universal contract.

Do not make the universal layer the highest authority. Local safety, privacy, data, scientific, release, and branch-ownership rules must override it.

For repositories with specialized semantics, create `.agents/<repo-or-domain>/OVERLAY.md` rather than forking the universal contract.
