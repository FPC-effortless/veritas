# Learning Efficiency

Learning Efficiency is a downstream capability-science objective built on learning-grade Machine Experience.

The governing question is:

> Under a fixed resource budget, does Veritas-directed experience selection and transformation produce more verified held-out capability gain than conventional training-data construction?

Veritas does not make GPUs cheaper and does not become a generic trainer. It aims to make each unit of data, teacher inference, human expertise, compute and money produce more verified capability.

## Separate axes

Keep these concepts independent:

- **Environment maturity** — whether an environment is executable, verifier-valid, scientifically qualified, frontier-qualified, training-validated and commercially releasable.
- **Experience maturity** — whether a MachineExperience is traceable, reverifiable, diagnostic, counterfactual, curriculum-ready, procedure-ready, abstraction-ready or continual-learning-ready.
- **Frontier usefulness** — whether the environment exposes meaningful strong-agent capability gaps.
- **Training usefulness** — whether a training intervention improves held-out capability.
- **Learning efficiency** — how much verified held-out capability gain is obtained per resource unit.

None implies another.

## Resource-normalized metrics

Report denominators separately rather than collapsing them into one score:

- capability gain per training example;
- capability gain per training token;
- capability gain per GPU-hour or equivalent compute unit;
- capability gain per teacher-model token/call;
- capability gain per human annotation/review hour;
- capability gain per unit monetary cost;
- optional gain per wall-clock time or tool call when measured.

Missing resource evidence remains unknown. Veritas must not invent GPU-hours, human time, costs or teacher usage.

## Failure-directed experience selection

The primary candidate loop is:

`evaluate -> identify failures -> build FailureFamily records -> derive CapabilityGap candidates -> select representative experience -> create targeted learning objects -> train externally -> reevaluate`

Selection is a hypothesis, not an assumption. Compare it against matched random/broad/control datasets under equal resource budgets.

## Experience multiplication

One expensive MachineExperience may produce multiple independently versioned derived objects:

- failed/negative example;
- corrected or recovery trajectory;
- preference pair;
- verifier-feedback example;
- alternative action;
- counterfactual experience;
- next-state prediction example;
- evidence-selection example;
- structured repair example;
- procedure candidate;
- curriculum challenge.

Every derivative must retain source-experience, verifier and evidence lineage. Derivation does not automatically make the object training-qualified.

## Capability-directed synthetic data

Synthetic generation should target a measured capability deficiency. Generated candidates should be verified, deduplicated/clustered, tested for saturation, structurally varied, and retained only when they contribute useful capability coverage. Raw generated volume is not itself a quality metric.

## Active curricula

Replace a fixed large dataset with an experimentally controlled frontier loop:

`measure capability frontier -> select/generate experiences near and above frontier -> train -> held-out reevaluation -> advance or revise frontier`

Curricula qualify only when they improve held-out acquisition efficiency relative to controls.

## Selective teacher routing

Teacher inference is a scarce budgeted resource. A future policy may skip teacher calls on student-verified-correct experiences and concentrate teacher intervention on uncertainty, verifier failures, novel failure families or new capability gaps. Reduced teacher spend alone is not success if capability gain falls.

## Parameter-efficient training

LoRA, QLoRA, SFT, RL and distillation implementations remain external backends. Veritas records the capability baseline, training-bundle identity, method/configuration provenance, resource usage, post-training evaluation, transfer/regression evidence and LearningEfficiencyReport.

## Minimum sufficient model

For a defined deployment threshold, Veritas may compare model size/cost against qualified capability performance and identify the smallest or lowest-cost model satisfying that threshold under a stated environment/tool/runtime/verifier distribution. This is a scoped operational finding, not a universal model ranking.

## Compute-constrained development

The mechanism is particularly relevant where compute, data and expert knowledge are scarce. A dedicated application program may test small specialized models across African operational domains such as local-language customer service, finance/mobile money, logistics, telecom, energy, SME accounting/commerce, agriculture, government/admin workflows, education administration and synthetic healthcare-administration worlds.

The hypothesis is not that better data erases frontier-pretraining compute gaps. It is that targeted verified experience can improve the capability obtained from limited fine-tuning/post-training resources.

## Equal-budget experiment

The first decisive experiment should compare several open pretrained models in roughly the 0.5B–7B range under identical data/compute/teacher/human budgets.

Control: conventional/random/broad training-example construction.

Treatment: `capability evaluation -> failure/gap discovery -> Veritas experience selection/transformation -> targeted training bundle -> same external training method -> held-out reevaluation`.

Pre-register model revisions, environment/verifier identities, seeds, resource budget, target capability, IID/OOD/adversarial panels, stopping rule and regression suite.

The strongest claim is supported only when the Veritas-directed treatment produces larger verified held-out capability gain per equal resource budget across replicated settings.

## Gold-10

High-Stakes Investigation / Gold-10 is an early experience source, not a dependency blocker. Acquisition and reconstruction proceed independently. When model/training experiments begin, retain actual candidate/selected counts, teacher usage, training examples/tokens, provider/model cost, measured compute, human review effort and before/after capability/failure-family evidence.

## Architecture boundary

The proposed Learning Engine may eventually include capability profiling, failure clustering, experience selection, curriculum generation, counterfactual generation, experience rewriting, training-data compilation, teacher routing, distillation planning, training-experiment records, model comparison and LearningEfficiencyReport.

These components are justified incrementally by measured experiments. Do not create them all as speculative scaffolding.