# Research adequacy migration

Execution-purpose declarations are explicit operator intent, not a classifier or
proof of scientific adequacy. An omitted purpose means `research`: a historical
recipe can still be inspected, but cannot silently launch a new research run
without its adequacy evidence. Historical records remain `UNASSESSED`; migration
must not rewrite their evidence or promote their conclusions.

## Shipped execution producers

The following producers are `engineering_diagnostic`. They exercise software
behavior with constructed or bounded examples, and cannot qualify scientific
claims. Some really train models; running an optimizer is not itself a research
adequacy assessment.

| Producer | Reason for non-claim execution |
| --- | --- |
| `trainlab/examples/linear.json`, `mean.json` | Constructed scalar training quickstart |
| `trainlab/examples/diagnose_dataset.py`, `diagnose_data_quality.py` | Injected dataset fault controls |
| `trainlab/examples/diagnose_models.py` | Constructed model-adapter diagnostic controls |
| `trainlab/examples/diagnose_experiments.py` | Scalar training and diagnostic acceptance controls |
| `trainlab/examples/diagnose_state.py` | State diagnostic fixtures |
| `trainlab/examples/diagnose_session_cost.py` | Session accounting fixtures, not efficiency qualification |
| `forge/examples/dataset_quickstart.py` | Constructed release/training integration example |
| `forge/examples/model_workflow.py` | Local model lifecycle software acceptance |
| `forge/examples/torch_workflow.py` | Real CPU framework acceptance, not architecture ranking |
| `research_lab/examples/run_acceptance.py` | Exact-store engineering diagnostics, zero model fits |
| `research_lab/examples/neural_loop_bootstrap.py` | Bounded GRU operational dispatch/replay acceptance |
| `research_lab/src/research_lab/ecosystem.py::_recipe` | Scripted-policy integration, no trained weights |

`research_lab/examples/changing_state_replay.py` is `historical_replay`: frozen
learned checkpoints are evaluated on previously exposed public DEV cases. It
preserves reproduction evidence, not fresh generalization or cost qualification.
All paths above are relative to `integrations/`.

Unit-test recipe constructors are explicitly `engineering_diagnostic`; their
purpose is to test execution, failure, recovery and evidence integrity. This does
not alter the default for user recipes. The dedicated adequacy tests retain
research-default recipes to test fail-closed admission.

## Caller boundaries

The CLI, dashboard launch, Research Lab queue, replication, memory campaign and
lifecycle preflight continue passing the caller's recipe to TrainLab. They must
not infer an exemption from a command name, checkpoint, lane name, or workload
kind. A replay of a research recipe must satisfy that recipe's evidence gate;
only a recipe explicitly restricted to historical replay can run unassessed.

Low-level diagnostic/session APIs are not proof of scientific adequacy. Their
coverage and report labels must remain distinct from admitted research and
scientific promotion. Purpose declarations are not a sandbox: trusted local
operators can execute code outside the ecosystem. The enforceable guarantee is
that supported admission/reporting paths do not silently treat missing evidence
as checked adequacy, not that software can guarantee a scientific hypothesis or
prevent arbitrary external execution.

## Migration verification

`integrations/trainlab/tests/test_example_purposes.py` inventories shipped recipe
producers, including generated Python dictionaries, and checks their explicit
purpose. Execution/integration suites check the producers still run under that
policy. Neither test supplies missing adequacy evidence to real research recipes.
