# Veritas agent system

This directory contains three layers:

- `universal/` — repo-agnostic coding contract designed to work in both Chat and Work modes;
- `veritas/` — Veritas-specific scientific, benchmark-integrity, privacy, qualification, and release constraints;
- `skills/` — adapted Matt Pocock skill names routed through the two contracts above.

The universal contract is intended to be copied into any repository. A repository should add an overlay rather than editing the universal semantics for local exceptions.
