# Commercial Validation Prospect Outreach

## Purpose
Recruit qualified AI-agent operators into the SRE Capability Audit experiment. This document is an execution aid, not evidence of traction.

## Ideal prospect
Prioritize organizations that already have an AI agent or tool-using automation performing a consequential operational workflow. Favor teams with a near-term model/agent release decision and an identifiable technical owner.

## Qualification questions
1. What workflow does the agent perform today?
2. What constitutes a correct end state?
3. What failures would create operational or financial risk?
4. How do you evaluate the workflow before deployment?
5. When is the next meaningful model/agent/harness change?
6. Who owns the deployment decision?

## Outreach principle
Lead with the operational problem, not the Veritas architecture. Ask for one workflow rather than asking the prospect to buy a platform.

## Default outreach
Subject: Independent test of one AI-agent workflow

I’m testing a capability-evaluation system for AI agents that verifies the actual operational end state, not just whether an agent produces a plausible answer.

If you have an agent performing a real SRE/operations workflow, I can run one capability audit against it and return the failure evidence and deployment implications.

The request is small: one workflow, its success criteria, and a reproducible way to execute the agent. There is no commitment to a platform purchase.

If the evaluation does not expose anything useful, that is also a useful result for the experiment.

Would one current workflow be suitable for a test?

## Follow-up
If there is no response, follow up once with a concrete example of the kind of failure the audit can distinguish: apparent task completion versus incorrect operational state, violated constraints, unsafe side effects, or failed recovery.

## Do not claim
- customer traction unless a real customer interaction occurred;
- commercial viability before the pre-registered experiment is complete;
- benchmark superiority without the corresponding controlled evidence;
- confidentiality, security, or deployment guarantees beyond the actual engagement scope.

## Evidence capture
Every qualified interaction must be recorded in `validation_tracker.md` with the date, segment, workflow, access status, evaluation status, finding, customer action, repeat behavior, and commercial outcome. Do not record unnecessary personal data.
