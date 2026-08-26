# Veritas Design-Partner Pilot — Statement of Work Template

> Operational template only. Complete seller identity, governing agreement, fees, payment terms, and any customer-required legal language before signature.

## 1. Parties and order details

**Seller:** [LEGAL ENTITY / SOLE PROPRIETOR NAME]  
**Customer:** [CUSTOMER LEGAL NAME]  
**Effective date:** [DATE]  
**Primary seller contact:** [NAME / EMAIL]  
**Primary customer contact:** [NAME / EMAIL]  
**Governing agreement:** [MSA / CUSTOMER TERMS / STANDALONE SOW]

## 2. Objective

Seller will evaluate the Customer's specified AI model/agent using **Veritas CompanyWorld Pilot v1** to answer the following primary decision question:

> [ONE-SENTENCE DEPLOYMENT / MODEL / HARNESS / CAPABILITY QUESTION]

## 3. Customer system under evaluation

- Model/agent: [IDENTIFIER]
- Harness/agent version: [VERSION]
- Integration: [OPENAI-COMPATIBLE ENDPOINT / AGENT ENDPOINT / CONTAINER / CLI]
- Attempts per task: [N]
- Token limit: [LIMIT]
- Tool/cost limit: [LIMIT]
- Wall-clock limit: [LIMIT]
- Retry policy: [POLICY]
- Allowed systems/tools: [LIST]

Any change to these fields during the private evaluation requires written agreement and may require a new run.

## 4. Services

Seller will:

1. integrate and validate the agreed evaluation interface;
2. conduct a development/dry run;
3. freeze the applicable private benchmark version/hash;
4. run the agreed private evaluation suite;
5. independently score the Customer system using Veritas verifiers;
6. classify meaningful failure modes;
7. deliver the artifacts described below;
8. conduct one readout session;
9. optionally quote a re-evaluation after Customer changes its system.

## 5. Deliverables

- evaluation manifest with benchmark/model/harness/budget metadata;
- private benchmark run identifier and benchmark hash;
- aggregate and relevant per-level/per-family scores;
- parse/format reliability;
- tool/budget/cost statistics where available;
- authority/policy/recovery metrics where applicable;
- representative successful and failed trajectories, subject to agreed redaction;
- prioritized capability gaps;
- recommended next experiments;
- final evaluation report/readout.

Private benchmark seeds, answer keys, hidden ground truth, evaluator oracles, and unreleased adversarial suites are not Customer deliverables.

## 6. Customer responsibilities

Customer will:

- provide timely access to the agreed model/agent interface;
- provide accurate model/harness/configuration information;
- provide revocable credentials through an agreed non-public channel;
- identify rate limits/network restrictions;
- not attempt to obtain private benchmark answers/oracles;
- identify any information that must be treated as confidential;
- review integration questions and the final readout promptly.

## 7. Acceptance

Technical acceptance follows [`evaluation-acceptance.md`](evaluation-acceptance.md) unless replaced by mutually agreed written criteria.

The evaluation is accepted based on valid execution and delivery of the agreed artifacts, **not** on achieving a minimum model score. A low score may be the correct outcome of the evaluation.

## 8. Data and security

The standard CompanyWorld pilot uses synthetic data and does not require production Customer business data.

If Customer supplies confidential or personal data, the parties will document any additional retention, deletion, DPA, subprocessor, storage-location, and security requirements before such data is processed.

Reusable credentials and Veritas private benchmark assets will not be committed to the public source repository.

## 9. Fees and payment

**Fixed pilot fee:** [AMOUNT / CURRENCY]  
**Inference/third-party compute:** [INCLUDED / PASS-THROUGH / CUSTOMER-PROVIDED]  
**Payment schedule:** [E.G. 50% ON SIGNATURE, 50% ON DELIVERY]  
**Payment due:** [E.G. NET 7 / NET 15]  
**Taxes/withholding:** [AS APPLICABLE]

Out-of-scope integration/custom benchmark work requires a written change order or separate quote.

## 10. Schedule

- Integration start: [DATE]
- Private evaluation window: [DATE/RANGE]
- Target readout: [DATE]

Dates depend on Customer access and responsiveness. Material Customer-caused access delays shift the schedule accordingly.

## 11. Intellectual property

Unless the governing agreement states otherwise:

- Seller retains ownership of Veritas software, benchmark methodology, private worlds, hidden truth, evaluator oracles, task generators, and reusable evaluation infrastructure.
- Customer retains ownership of its models, prompts, harnesses, credentials, and pre-existing materials.
- Customer receives the agreed rights to use its delivered evaluation report internally.
- Ownership/use of customer-specific adapters, trajectories, derived benchmark mutations, and publicity/case-study rights must be stated explicitly in the signed agreement or order form.

## 12. Confidentiality and publicity

Confidentiality is governed by [NDA / MSA / CUSTOMER TERMS]. Neither party may use the other's name/logo or publish pilot results without written permission unless already permitted by the governing agreement.

## 13. Change control

Changes to benchmark scope, integration type, number of systems/models, private-suite size, custom task/world requirements, or report obligations may affect price and schedule and require written approval.

## 14. Signatures

**Seller**  
Name: ____________________  
Title: _____________________  
Date: ______________________

**Customer**  
Name: ____________________  
Title: _____________________  
Date: ______________________
