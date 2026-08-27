---
name: tdd
description: Use red-green-refactor or the analogous falsifier-first loop at an observable seam.
---
# tdd
RED: create a failing behavioral test/reproduction/falsifier. GREEN: smallest coherent change. REFACTOR: improve structure while preserving behavior. Expand verification after the local loop is trustworthy. Do not compute expected values with the same implementation being tested. For benchmarks/environments, test verifier/transition semantics independently from the policy being evaluated.
