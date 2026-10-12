# Bootstrap reconciliation for unheld BLOCKED work

`/roadmap-bootstrap` normally preserves existing trusted agent-work status. Mutable Work Contract state and labels are discovery metadata after trusted status exists and must not overwrite an active or transitioned holder record.

There is one narrow reconciliation exception for bootstrap-created deadlocks. Repository OWNER bootstrap may move a trusted record from `BLOCKED` to `READY` only when the record is still pristine and unheld: `github_actor`, `agent_id`, `branch`, claim/heartbeat timestamps, linked PR, and linked PR head are all null; `transition_seq` and `last_command_comment_id` are zero; `released_reason` is null; `return_state` is `BLOCKED`; the blocker is exactly `bootstrap/reconciliation required`; the frozen `ownership_paths` snapshot already exists; and the current Work Contract declares initial state `READY`.

The transition clears only the bootstrap blocker and changes `state` and `return_state` to `READY`. It preserves the frozen ownership snapshot exactly. Because there is no holder, it creates no global source reservation. Bootstrap then reconciles the issue label to `work:ready`.

The exception must fail closed for any record that has been claimed, recovered, released, explicitly blocked, handed off, completed, superseded, or otherwise transitioned. In particular, editing a Work Contract cannot reset a holder, clear an arbitrary blocker, replace frozen ownership, or make REVIEW/DONE/SUPERSEDED work READY.

ROADMAP-LOCK-005 exists to make dependency resolution auditable for bootstrap-derived unheld work such as #286 without restoring the old behavior where mutable issue text could become execution authority.
