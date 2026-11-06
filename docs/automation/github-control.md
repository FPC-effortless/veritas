# Authorized GitHub Automation Control

The `Authorized GitHub Dispatch` workflow provides an auditable bridge for automation clients that
can create issue comments but cannot call the Actions workflow-dispatch API directly.

## Control issue

Commands are accepted only on an ordinary issue titled exactly `Veritas automation control` and
only when the commenter’s GitHub author association is `OWNER`, `MEMBER`, or `COLLABORATOR`.
Pull-request comments are rejected.

The first line must contain exactly one allow-listed command:

```text
/veritas-dispatch ci
/veritas-dispatch security
/veritas-dispatch python-quality
/veritas-dispatch portability-convergence
/veritas-dispatch portability-validation
/veritas-dispatch projectworld-qualification
```

Every target is dispatched on `main`. In particular, the sealed portability workflow cannot be
pointed at an arbitrary feature branch that could exfiltrate repository secrets. Release,
publishing, model-training, and other expensive/private workflows are intentionally excluded from
the allow-list and retain their existing authority boundaries.

The issue-comment event, Actions run, and acknowledgement comment form the audit trail. A dispatch
acknowledgement is not qualification evidence; the target workflow result and exact head commit
must still be inspected.
