# Running the Continuous Agent Capability Observatory

Veritas can now execute real CompanyWorld longitudinal cells against hosted or local models.

## Live path

```text
public CompanyWorld bundle + private oracle bundle
                    ↓
         bundle fingerprint / WorldRef
                    ↓
        frozen anchor ScenarioRefs
                    ↓
 model × harness × verifier × execution × snapshot
                    ↓
            LongitudinalCells
                    ↓
      LocalObservatoryScheduler
                    ↓
 CompanyWorldJSONAgentHarness
       ↙                    ↘
model provider          CompanyWorld tools
       ↘                    ↙
             RolloutTrace
                    ↓
        independent verifier
                    ↓
            CapabilityRun
                    ↓
      repeated-seed aggregate
                    ↓
    longitudinal drift report
```

The model never receives the private oracle. The baseline harness exposes only the public task,
permitted systems, current budget state, and observations returned by `search`, `search_all`, and
`open_record`. Submission is scored by the existing CompanyWorld verifier.

The world version is a content fingerprint over the public bundle and private oracle bundle. A
change to either creates a new environment version rather than silently contaminating a
longitudinal comparison.

## Providers

The live runner currently supports:

- `openai`: OpenAI Responses API using `OPENAI_API_KEY` by default. Requests force `store=false`.
- `huggingface`: Hugging Face Inference Providers through its OpenAI-compatible router using
  `HF_TOKEN`.
- `compatible`: any OpenAI-compatible chat-completions endpoint, including many hosted routers,
  vLLM, TGI/HUGS, and compatible local servers.
- `local`: an argv-based subprocess adapter. It does not invoke a shell and can wrap local model
  CLIs or a custom inference program.

Provider credentials are read from environment variables and are not copied into cells, traces,
or run metadata.

## CLI

Install the package, then use the `veritas-observe` command.

### Hugging Face

```bash
export HF_TOKEN=...

veritas-observe companyworld \
  --public-bundle companyworld_distribution.json \
  --oracle-bundle companyworld_oracles.json \
  --provider huggingface \
  --model openai/gpt-oss-20b:cheapest \
  --model-snapshot provider-current \
  --split public_eval \
  --limit 10 \
  --max-workers 2 \
  --store-root observatory_data
```

### OpenAI Responses

```bash
export OPENAI_API_KEY=...

veritas-observe companyworld \
  --public-bundle companyworld_distribution.json \
  --oracle-bundle companyworld_oracles.json \
  --provider openai \
  --model YOUR_MODEL_ID \
  --model-snapshot YOUR_MODEL_SNAPSHOT \
  --split public_eval \
  --limit 10 \
  --store-root observatory_data
```

### OpenAI-compatible endpoint

```bash
export MODEL_API_KEY=...

veritas-observe companyworld \
  --public-bundle companyworld_distribution.json \
  --oracle-bundle companyworld_oracles.json \
  --provider compatible \
  --provider-id my-router \
  --base-url https://example.invalid/v1 \
  --api-key-env MODEL_API_KEY \
  --model my-model \
  --split public_eval
```

### Local CLI

The subprocess adapter sends the current prompt on stdin. With `--local-json-stdin`, stdin is a
JSON object containing the model id, prompt payload, and call parameters.

```bash
veritas-observe companyworld \
  --public-bundle companyworld_distribution.json \
  --oracle-bundle companyworld_oracles.json \
  --provider local \
  --model local-model \
  --local-command 'my-agent-cli --model {model}' \
  --split public_eval
```

## Budgets

The live runner separates provider and environment budgets:

- `--provider-cost-budget`: monetary model-provider budget. Accurate enforcement requires model
  pricing to be supplied with `--input-cost-per-million` and `--output-cost-per-million` when the
  endpoint does not report monetary cost.
- `--token-budget`: stops the baseline harness after observed provider usage reaches the limit.
- `--time-limit-s`: bounds provider calls and stops the agent loop after the observed elapsed
  duration. It is not a process-level kill of arbitrary harness code.
- `--tool-call-budget`: CompanyWorld tool-call limit.
- `--world-cost-budget`: CompanyWorld's abstract investigation-tool cost budget.

## Longitudinal operation

Each invocation creates a time-stamped cell snapshot unless `--time-snapshot` is explicitly
provided. Anchor scenarios keep the same scenario identity and seed while time/model snapshots
change. The cycle runner compares the new repeated-seed aggregate with the latest historical
aggregate whose world, model family/configuration, harness, verifier, execution config, runtime,
and taskset versions are identical.

Artifacts are written below the store root:

```text
observatory_data/
├── runs.jsonl
└── cycles/
    ├── CYCLE-....json
    └── CYCLE-....json
```

A cycle report contains scheduler outcomes, current aggregates, and any comparable longitudinal
drift reports. This command can be invoked by cron, GitHub Actions, a cloud scheduler, or a future
Veritas distributed scheduler without changing the cell/run contracts.
