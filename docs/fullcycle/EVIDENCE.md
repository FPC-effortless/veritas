# Executed evidence — 1 November 2026

The small engineering lifecycle completed on both backends. Neither model is a useful assistant.

| Run | Parameters | Updates | Initial validation NLL | Pretrained NLL | Final NLL | Training time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FULLCYCLE-001-verified (BPE-512) | 1,438,992 | 580 | 6.2569 | 3.9364 | 3.8825 | 177.0 s |
| FULLCYCLE-002 (byte-256) | 100,370 | 580 | 5.5480 | 2.1622 | 2.1658 | 59.8 s |

NLL is per token; byte/BPE losses and unequal sizes cannot be ranked directly.

## Passed engineering checks

- Real pretrain, midtrain, assistant-only SFT, frozen-reference DPO and policy-generated GRPO updates on both models.
- 158 checks: 13 new, 38 TrainLab, 68 Forge and 39 qualification regression checks.
- All 13 new checks independently rerun in development review.
- CLI pause/resume, completed-stage skipping and artifact verification.
- Injected crash between checkpoint blob and pointer publication, with exact control weights after recovery.
- Both registry models loaded using built, installed wheels outside the checkout.
- Local HTML chat, rejected CSRF, malformed-input handling and actual streamed generation.
- Identical releases from 2,149,737,022 input bytes twice, with 22,503,424-byte peak process RSS.

## Failed capabilities and limits

General-text replay repaired the pilot’s large language regression. Expanded generation still yielded only 17/26 validation and 6/31 test exact matches, dominated by binary examples. Both final models scored 6/19 on test integer comparisons versus a constant-majority diagnostic of 13/19. Their 17/21 validation decision score also equals that panel’s majority baseline. Free-chat samples are poor. These results establish no useful instruction, reasoning or RL gain.

GPU and mixed-precision training did not run. Two-rank Gloo startup was attempted and blocked by socket permissions. Distributed correctness/replay remain unverified; the new manual workflow was not dispatched. Full-operation FLOPs remain unknown; supported-operator counts and a separate 6N heuristic are reported.

No protected Veritas panel was opened. Outputs remain NOT_QUALIFIED, execution attestation UNKNOWN and training_validated=false. Full numbers and failed samples are in [EVIDENCE.json](EVIDENCE.json). This is a bounded training reference, not a 100M–500M capability demonstration or a production-scale platform.

Training artifact source commit: `816d1891041ad8749770d83e5abb1c6dd60c88b7`. A subsequent typing correction loads optional evaluation providers at runtime; it does not alter training or evaluation mathematics. Recorded training source hashes remain those of the training commit.
