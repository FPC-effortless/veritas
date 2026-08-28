---
name: wizard
description: Guide human-only authentication, secrets, irreversible setup, or administrative actions safely and minimally.
---
# wizard
Use only when the agent cannot legitimately perform the step. Before inventing automation, prefer an existing official platform feature, standard tool, or already-installed CLI/API. Explain purpose, hide secrets, never print/commit credentials, confirm irreversible actions, validate each step, and make reruns safe. Avoid wrappers/scripts for a one-off command unless they create a real safety/reproducibility benefit. For Veritas, never expose private benchmark keys/bundles or convert manual sealed-panel workflows into ordinary automation without explicit authorization.
