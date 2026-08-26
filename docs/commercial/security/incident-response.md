# Veritas Incident Response Policy

Status: operational policy template for pilots. This is not a certification or representation that any specific control framework has been audited.

## Incident definition

A security incident is a confirmed or reasonably suspected event affecting the confidentiality, integrity or availability of customer data, credentials, private benchmark truth, or the evaluation service.

Examples include:
- exposed or misused customer credentials;
- unauthorized access to customer-supplied artifacts;
- accidental disclosure of hidden benchmark truth to an evaluated agent;
- material corruption of private evaluator state or reports;
- compromise of the evaluation runner/container;
- unauthorized third-party access to retained evaluation traces.

## Response lifecycle

1. **Detect and record** — open an incident record with timestamp, affected run/customer, evidence and reporter.
2. **Contain** — stop affected evaluation runs, revoke/rotate exposed credentials, isolate affected runners or artifacts, and preserve forensic evidence.
3. **Assess** — determine affected data, access paths, time window, benchmark integrity impact and customer impact.
4. **Remediate** — patch the root cause, invalidate affected benchmark/run artifacts when necessary, and add regression/security tests.
5. **Notify** — notify affected customers without undue delay when a confirmed incident materially affects their data or evaluation integrity, subject to contract/legal requirements.
6. **Recover** — restore clean infrastructure and rerun affected evaluations only from a verified state.
7. **Post-incident review** — document root cause, timeline, corrective actions and any foundry/verifier challenge generated from the failure.

## Severity

- **SEV-1:** confirmed credential/customer-data compromise, evaluator private-truth compromise affecting external validity, or broad service compromise.
- **SEV-2:** contained security breach or material evaluation-integrity incident with limited scope.
- **SEV-3:** low-impact security/control failure without confirmed unauthorized disclosure.
- **SEV-4:** suspected event or near miss requiring investigation.

## Credential handling

If a credential may have been exposed, revoke/rotate first and investigate second. Credentials must never be copied into evaluation reports, trace artifacts, benchmark manifests or issue trackers.

## Benchmark integrity incidents

A hidden-truth leak or verifier exploit is treated as an integrity incident even when no customer data is affected. Affected task/version IDs must be quarantined until the exploit is reproduced, verifier tests are strengthened and a fresh private benchmark version is issued if required.

## Evidence and communication

Keep an incident timeline and decisions. Customer communications should state known facts, scope, containment status, actions required from the customer, and planned follow-up without speculation.
