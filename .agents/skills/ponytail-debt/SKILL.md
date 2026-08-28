---
name: ponytail-debt
description: Harvest deliberate `ponytail:` simplification comments into a read-only debt ledger with ceilings and upgrade triggers.
---
# ponytail-debt
Search source comments for `ponytail:` while excluding VCS metadata, dependency caches, and build output. Include language-appropriate comment prefixes. One row per marker, grouped by file: `<file>:<line>, <simplification>. ceiling: <limit>. upgrade: <trigger/path>.` Tag any marker with no real upgrade trigger as `no-trigger`; optionally add ownership from blame/history when useful. End with `<N> markers, <M> with no trigger.` If none: `No ponytail: debt. Clean ledger.` Read/report only. Persist a ledger file only when explicitly requested.
