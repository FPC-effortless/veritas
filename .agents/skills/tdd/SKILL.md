---
name: tdd
description: Use red-green-refactor or the analogous falsifier-first loop at an observable seam while keeping the test surface minimal.
---
# tdd
RED: create the smallest failing behavioral test/reproduction/falsifier that proves the requested behavior or bug. GREEN: apply the universal minimality ladder and make the smallest coherent change. REFACTOR: improve structure only where the now-proven behavior needs it; do not create speculative abstractions. Expand verification after the local loop is trustworthy. Do not compute expected values with the same implementation being tested. For benchmarks/environments, test verifier/transition semantics independently from the policy being evaluated. Non-trivial new logic must retain at least one runnable check; a trivial stdlib/native substitution introducing no new behavior need not add a ceremonial test if existing verification covers it.
