# Study — task → local-model mapping, grounded in benchmarks (June 2026)

Why this exists: hibrid maps each task to the *axis* it actually needs and to the best local model
for that axis **that fits the machine**. This study is the evidence behind the scores in
`backend/models_catalog.py` and the tiers in `docs/MODELS.md`. Research was run by four parallel
agents (code / writing+multilingual / reasoning / hardware); every number below is sourced.

## 1. Code axis (HumanEval+, BigCodeBench-Complete, LiveCodeBench)

| Model | Params | HumanEval+ | BCB-C | LiveCodeBench | code score |
|---|---|---|---|---|---|
| Qwen2.5-Coder-32B | 32B | ~88 | — | ~45 | 0.97 |
| Qwen2.5-Coder-14B | 14B | 87.2 | 48.4 | 37.1 | 0.90 |
| Qwen2.5-Coder-7B | 7B | 84.1 | 41.0 | ~29 | 0.79 |
| DeepSeek-Coder-V2-Lite (16B MoE) | 16B | ~76 | ~38 | 24.3 | 0.71 |
| Qwen2.5-Coder-3B | 3B | 80.5 | 35.8 | ~17 | 0.67 |
| Phi-4-mini | 3.8B | 68.3 | 43.0 | ~18 | 0.66 |
| Llama-3.1-8B | 8B | 59.8 | ~30 | ~12 | 0.51 |
| Gemma2-9B | 9B | 48.8 | ~27 | ~10 | 0.43 |

Takeaway: **Qwen2.5-Coder dominates every size tier.** Phi-4-mini is the best non-Qwen small coder.
Llama/CodeGemma trail badly. Quantization: Q4_K_M costs 1–4 pts on HumanEval+; prefer Q5/Q6 for code.
Sources: [Qwen2.5-Coder report](https://arxiv.org/html/2409.12186v3), [EvalPlus](https://evalplus.github.io/leaderboard.html), [BigCodeBench](https://bigcode-bench.github.io/), [LiveCodeBench](https://livecodebench.github.io/).

## 2. Writing / general / multilingual (IFEval, MMLU, MT-Bench, Arena-Hard + Spanish)

| Model | Params | IFEval | MMLU | gen/write score |
|---|---|---|---|---|
| Qwen3-8B | 8B | 85.0 | 85.9 | 0.90 |
| Qwen3-4B | 4B | 81.9 | ~83 | 0.84 |
| Qwen2.5-14B | 14B | 81.0 | 79.7 | 0.83 (MT-Bench 8.88) |
| Gemma2-9B | 9B | 74.0 | 71.3 | 0.75 (Arena Elo 1187) |
| Qwen2.5-7B | 7B | 71.2 | 74.2 | 0.74 (MT-Bench 8.75) |
| Llama-3.1-8B | 8B | ~76 | 69.4 | 0.72 |
| Llama-3.2-3B | 3B | 77.4 | 63.4 | 0.64 |
| Phi-3.5-mini | 3.8B | ~59 | 69.0 | 0.57 (repeats in long-form) |

- **Best small writer / instruction follower: Qwen3-8B** (dethrones Qwen2.5-14B at half the size).
- **Spanish writing:** Qwen3 (119-lang pretraining) or proven Qwen2.5-7B; Mistral-Nemo-12B for long ES docs (128K ctx).
- **Translation specifically: Aya-Expanse-8B** — purpose-built for 23 languages; m-ArenaHard 76.6% win,
  Dolly multilingual 83.9% vs Llama-3.1-8B. Qwen3-8B if you want one model for write+translate.

Sources: [Qwen3 report](https://arxiv.org/abs/2505.09388), [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/), [Aya-Expanse](https://arxiv.org/abs/2412.04261), [Gemma 2](https://arxiv.org/html/2408.00118v1), [BenchMAX](https://arxiv.org/pdf/2502.07346), [La Leaderboard ES](https://arxiv.org/pdf/2507.00999).

## 3. Reasoning / math (GSM8K, MATH-500, GPQA, AIME)

| Model | Params | MATH-500 | GPQA◆ | AIME-24 | reasoning score |
|---|---|---|---|---|---|
| Phi-4-reasoning-plus | 14B | ~96 | 69.3 | 81.3 | 0.99 |
| R1-Distill-Qwen-14B | 14B | 93.9 | 59.1 | 69.7 | 0.85 |
| Qwen3-14B (thinking) | 14B | ~95 | ~57 | ~62 | 0.81 |
| Phi-4 (non-reasoning) | 14B | 80.4 | 56.1 | — | 0.75 |
| Phi-4-mini-reasoning | 3.8B | 94.6 | 52.0 | 57.5 | 0.73 |
| R1-Distill-Qwen-7B | 7B | 92.8 | 49.1 | 55.5 | 0.68 |
| R1-Distill-Qwen-1.5B | 1.5B | 83.9 | 33.8 | 28.9 | 0.36 |
| Qwen2.5-14B (standard) | 14B | 55.6 | 32.8 | — | 0.31 |
| Llama-3.1-8B | 8B | 48.6 | 23.7 | — | 0.14 |

- The reasoning divide is sharp: **standard models <0.35 are near-random on GPQA — do not trust them.**
- A 14B *reasoning* model (Phi-4-reasoning-plus, R1-Distill-14B) genuinely solves what same-size
  standard models cannot; worth running locally on 24 GB.
- **Cost of "thinking":** 2–5× output tokens. A Q4 14B at ~12–15 t/s spends ~130–165 s on a
  2000-token trace before the answer. Budget it; disable thinking for chat/writing.
- Escalate to frontier when you need GPQA >70% or AIME-25 >80% (still unreachable locally).

Sources: [DeepSeek-R1](https://arxiv.org/html/2501.12948v1), [Phi-4-reasoning](https://arxiv.org/pdf/2504.21318), [Phi-4-mini-reasoning](https://arxiv.org/pdf/2504.21233), [Qwen3 report](https://arxiv.org/abs/2505.09388).

## 4. Hardware sizing

Footprint (weights only): `RAM ≈ params_B × (bpw/8) × 1.10`. Q4_K_M ≈ 0.60 GB/B. **KV-cache is
additive** and grows with context — an 8B model adds ~0.3 GB @2K, ~1 GB @8K, ~5 GB @32K, ~20 GB @128K.

| Model | Q4_K_M | Q5_K_M | Q8_0 | FP16 |
|---|---|---|---|---|
| 3B | 1.9 | 2.3 | 3.9 | 6.4 |
| 7B | 4.4 | 5.2 | 6.9 | 14.0 |
| 8B | 4.9 | 5.7 | 7.7 | 16.1 |
| 14B | 8.7 | 10.3 | 16.0 | 29.5 |

Quality vs quantization (Llama-3.1-8B, WikiText-2 perplexity): FP16 7.32 → Q8 7.33 → Q6_K 7.35 →
Q5_K_M 7.40 → **Q4_K_M 7.56** → Q3_K_M ~7.80. Benchmark deltas at Q4_K_M are within noise for general
tasks; code/math benefit from Q5/Q6.

Throughput (decode, Q4, 2K ctx): 8-core CPU ~5–8 t/s (7B); Apple M2 ~18 t/s (7B); RTX 3060 ~42 t/s
(7B); RTX 4090 ~135 t/s (7B). Decode is memory-bandwidth-bound; prefill is compute-bound. **>15 t/s**
is the practical floor for interactive use.

### Machine tiers (largest interactive model in Q4)

| Tier | Hardware | Max model | tok/s |
|---|---|---|---|
| cpu_small | ≤8 GB RAM, no GPU | 3B | 5–10 |
| cpu_large | 16–32 GB RAM / Apple 16 GB | 7B | 8–22 |
| gpu_12gb | GPU 8–12 GB | 8B (14B short-ctx only) | 25–52 |
| gpu_24gb | GPU 24 GB+ / Apple 32–64 GB | 32B (70B on 64 GB unified) | 35–135 |

Sources: [llama.cpp quant eval](https://github.com/ggml-org/llama.cpp/discussions/2094), [KV-cache math](https://lyceum.technology/magazine/kv-cache-memory-calculation-llm/), [Apple Silicon benchmarks](https://modelpiper.com/blog/local-llm-benchmarks-apple-silicon), [GPU inference](https://github.com/XiongjieDai/GPU-Benchmarks-on-LLM-Inference).

## How this lands in the router

1. `classifier.py` infers a `task_type` (now incl. `write`, `translate`, `code`).
2. `task_policy.py` maps `task_type → axis` (general/writing/code/reasoning/multilingual) + tier ladder.
3. `models_catalog.best_local_for(axis, available, max_params_b)` picks the highest-capability model
   on that axis **that fits** (then smallest at a tie, for speed/cost).
4. `models_catalog.tier_for(hw)` recommends what to *install* per machine class (served at `/v1/policy`).
