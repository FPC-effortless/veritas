# Continuous Verifier Exploit Monitoring

Verifier qualification is a point-in-time decision. Continuous exploit monitoring preserves every
known verifier failure as an append-only regression obligation for later verifier versions.

This layer observes verifier behavior. It does not modify canonical scores, silently patch a
verifier, or substitute for the full Verifier Qualification Suite.

## Artifact model

`ExploitFinding` records immutable discovery facts:

- exploit class and severity;
- affected environment and verifier identity;
- a content-addressed reproducer/evidence reference;
- discovery source;
- optional environment/verifier version scope;
- disclosure level and provenance.

The corpus stores references, not raw private reproducer payloads. Operator-private evidence can
remain in sealed storage while its identity and authorized reference are retained.

`ExploitDisposition` provides append-only lifecycle history:

```text
OPEN → FIXED
  └──→ SUPERSEDED
FIXED → OPEN       (regression reopened)
FIXED → SUPERSEDED
```

The initial record must be `OPEN`. Later records form a contiguous identity chain. `FIXED` requires
regression evidence; `SUPERSEDED` requires another retained finding and is terminal. Fixed records
never replace or delete the discovery record.

## Target-version monitoring

`monitor_exploits` selects all non-superseded findings applicable to an exact environment/verifier
version and requires one `ExploitRegressionObservation` for each. Findings with no explicit version
scope apply to later versions and must be rerun.

The batch report separates four gates:

1. applicable exploit replay coverage;
2. known-exploit regression resistance;
3. unresolved severe exploits;
4. canonical score parity.

Missing, errored, or not-run replay evidence is always `UNKNOWN`; policy cannot waive this gate. A known exploit that still succeeds is
`FAIL`. An `OPEN` high/critical finding blocks the monitor report even if an ad hoc replay happens to
be blocked; the fix must be reviewed and appended with its regression evidence. A score-parity
failure proves that the monitoring layer did not merely observe canonical verifier output and also
fails the report.

The report is qualification evidence only. It does not itself change verifier or training maturity.
Later convergence work may bind its content-derived report identity to those gates without changing
the verifier implementation.

## Buyer-safe summary

`buyer_safe_summary` includes aggregate applicable/blocked/active/unknown/severe counts. It lists
individual findings only when their disclosure level is `PUBLIC`. It omits private exploit IDs,
reproducer/evidence IDs, hashes, references, private report/corpus identities, and payloads. Its
own identity is derived only from the sanitized summary contents.

Buyer-safe status is still bounded: a green exploit-monitor report means the retained applicable
regression corpus passed for one exact target version. It is not proof that undiscovered exploits do
not exist.
