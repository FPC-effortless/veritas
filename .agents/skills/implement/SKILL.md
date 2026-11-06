---
name: implement
description: Implement an approved task through isolated execution, falsifier-first development, minimal solution selection, verification, and review.
---
# implement
Read governing context and active ownership rules. Define outcome/falsifier. Trace the real path and relevant callers. Work on a task branch/worktree/sandbox. Use `tdd` or the task-appropriate falsifier loop. Before adding code, apply the universal ladder: need? reuse? stdlib? native platform? installed dependency? direct one-line form? only then minimum new code. For bugs, prefer one root-cause fix at the common seam over duplicated symptom patches. Avoid speculative abstractions/config/scaffolding. If a deliberate simplification has a real ceiling, mark `ponytail: <ceiling>, <upgrade trigger/path>`. Run targeted then broader verification, including at least one runnable check for non-trivial new logic. Capture evidence and unrun gates. Run `code-review`. Open/propose a PR. Do not merge/deploy/release or trigger expensive/manual workflows unless authorized by the active task.
