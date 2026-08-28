---
name: ponytail-audit
description: Scan the whole repository for over-engineering and rank what can be deleted, reused, or replaced with stdlib/native capabilities.
---
# ponytail-audit
Repo-wide `ponytail-review`. Hunt dependencies duplicating stdlib/native features, one-implementation interfaces, one-product factories, delegate-only wrappers, semantically empty files/layers, dead flags/config, and hand-rolled standard-library behavior. Use `delete`, `stdlib`, `native`, `yagni`, and `shrink` tags. Rank biggest credible cut first with file/path and replacement. Optionally summarize `net: -N lines, -M deps possible` as an estimated future reduction, not measured savings. Correctness, security, and performance are out of this pass and route to normal `code-review`. Read/report only unless fixes are separately authorized.
