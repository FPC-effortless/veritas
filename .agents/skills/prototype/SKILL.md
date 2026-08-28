---
name: prototype
description: Build the smallest disposable prototype that answers one explicit question without contaminating production or benchmark state.
---
# prototype
State the question first. Use the first rung of the minimality ladder that can answer it: reuse/native/stdlib before new prototype machinery. Isolate the prototype; avoid production credentials, irreversible effects, sealed/private data, release artifacts, production abstractions, framework additions, and generalized scaffolding. Expose only enough internal state to evaluate the question. Leave the smallest runnable check that distinguishes success from failure when the experiment has non-trivial logic. Record what remains unsolved for production. A prototype proves only the question it was designed to answer.
