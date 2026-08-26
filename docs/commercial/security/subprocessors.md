# Veritas Subprocessor Register

Status: template. Populate only with providers actually used for a specific customer delivery.

A provider should be listed here only when it processes customer personal data or confidential customer content on Veritas's behalf. Merely being a development dependency does not make a service a customer-data subprocessor.

| Provider | Purpose | Data categories | Processing location | Retention | Status |
| --- | --- | --- | --- | --- | --- |
| Customer-selected model/API provider | Model inference when Veritas calls a customer-authorized external endpoint | Evaluation prompts/observations included in the agreed run | Customer/provider-specific | Provider/customer-specific | Customer-selected; document per SOW |
| GitHub | Source control/CI for Veritas software; do not place customer credentials or production customer data in CI artifacts | Normally no customer content; synthetic benchmark fixtures only | Provider-specific | Provider-specific | Engineering infrastructure |

## Delivery rule

For a pilot, produce a customer-specific subprocessor attachment before execution. Remove rows for services not involved in that delivery and add any actual hosting, inference, logging, storage or support provider that will receive customer data.

## Changes

Material additions of subprocessors that process customer data should follow the notice/objection mechanism specified in the applicable DPA or SOW.

## Data minimization

Prefer configurations in which customer endpoints are called directly from an isolated runner and raw customer content is not persisted outside the agreed evaluation boundary.
