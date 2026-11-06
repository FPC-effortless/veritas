# Contributing

Veritas, Forge, TrainLab and Research Lab OS share this repository. Start with the
[ecosystem guide](docs/ecosystem/README.md) and each component's README. Public
project-authored software uses Apache-2.0; [LICENSING.md](LICENSING.md) defines the
separate boundary for private benchmarks, customer assets and third-party data.
Contribute only material you have permission to submit under the applicable
license. Keep existing copyright, attribution and third-party notices.

## Set up a development checkout

Use Python 3.12+ for the full ecosystem. From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]' ./integrations/forge ./integrations/trainlab ./integrations/research_lab
python -m pip install -r requirements-quality.txt
veritas-ecosystem run .trainlab/first-comparison
veritas-ecosystem verify .trainlab/first-comparison
```

The example needs no account, API key, hosted service, torch installation or paid
compute after installation. It uses public constructed cases and two scripted
policies. This demonstrates software operation, not scientific qualification.
For a smaller setup, install only the package you are changing; see the
[compatibility matrix](docs/ecosystem/compatibility.md).

## Propose and implement a change

Search existing issues and documentation first. Use a bug report for a concrete
failure, a feature request for a user workflow, and the existing architecture
proposal form for a new owned infrastructure boundary. Keep large changes small
enough to inspect and reproduce. Veritas integrates commodity trainers, tracking,
execution and hosting rather than duplicating those platforms.

Work on a task branch. State the outcome, affected component, falsifier, trust
boundaries and compatibility expectations. Add a runnable regression check for
nontrivial behavior, run the affected suite, then broaden checks as appropriate.
Record exact commands, failures and unrun checks in the PR. Do not edit a quality
baseline to admit diagnostics introduced by your change.

```bash
python -m pytest tests/unit/test_shared_evidence_contract.py tests/unit/test_ecosystem_quickstart.py
python -m unittest discover -s integrations/trainlab/tests -v
python -m unittest discover -s integrations/forge/tests -v
python -m unittest discover -s integrations/research_lab/tests -v
python tools/quality_baseline.py check
```

The ecosystem test requires the sibling packages; a skipped optional test is not
a PASS. GPU fits, external-provider jobs, sealed-panel evaluations and manual
release workflows need their explicit task scope and resource authority. They
are not ordinary contributor smoke tests. Follow [AGENTS.md](AGENTS.md) when using
coding agents; its source-bound review and private-data rules apply equally to
human-assisted and agent-assisted work.

## Protect data and evidence

Use redistributable public or constructed fixtures for tests. Never include
secrets, customer data, hidden labels, protected TEST rows or operator-private
reports in issues, PRs or public CI artifacts. A hash proves identity, not source
permission or independent scientific validity. Preserve negative findings and
missing-evidence states; do not weaken a gate or relabel an unknown result to make
a change pass. Follow [SECURITY.md](SECURITY.md) for vulnerabilities.

A new contributor does not need an external account to run the public example.
Maintainers may label bounded, documented issues `good first issue` or
`help wanted` after reviewing their scope; those labels are not a promise of
support, payment or acceptance. [GOVERNANCE.md](GOVERNANCE.md) describes review and
release decisions.
