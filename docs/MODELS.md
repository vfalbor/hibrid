# hibrid — model / machine mapping

hibrid doesn't pick a local model by "does it fit in memory" alone. It keeps a curated catalog
of small models known to perform acceptably, scored **per task axis**, and combines that with the
machine's measured speed. The mapping lives in `backend/models_catalog.py`; routing picks the best
**available** model that fits the machine and is competent for the detected task. The live mapping
(and your node's detected tier) is served at `GET /v1/policy`.

## Task axes (what "competent" means)

A task is reduced to one of five axes. Each axis is benchmarked differently, so a model that is
great at code can be weak at reasoning — the router scores the axis the task needs, not a blob.

| Axis | What it measures | Key benchmarks |
|---|---|---|
| `general` | knowledge + instruction following | MMLU, IFEval, Arena-Hard |
| `writing` | drafting / copy / summaries / long-form | MT-Bench, EQ/Creative-Writing, IFEval |
| `code` | code generation | HumanEval+, BigCodeBench, LiveCodeBench |
| `reasoning` | multi-step logic + math | GSM8K, MATH, GPQA, AIME |
| `multilingual` | non-English (Spanish) + translation | FLORES, m-ArenaHard, La Leaderboard (ES) |

Task → axis: `code`/detected code → `code`; `deep_reason` → `reasoning`; `write` → `writing`;
`translate` → `multilingual`; otherwise `general`.

## Curated small models

Capability scores (0–1) are **normalized priors from public benchmarks (June 2026)** — see Sources
below — refined online by the node's own history. ⚠ = "thinking" model: its `reasoning` score
assumes chain-of-thought mode (2–5× tokens/latency); use normal mode for chat/writing.

| Model | Params | ~RAM Q4 | gen | write | code | reason | multi | Best for |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:32b | 32B | ~20 GB | 0.80 | 0.74 | **0.97** | 0.50 | 0.64 | top code (24 GB GPU) |
| qwen2.5-coder:14b | 14B | ~8.7 GB | 0.74 | 0.70 | **0.90** | 0.45 | 0.60 | best coder <16B |
| qwen2.5-coder:7b | 7B | ~4.5 GB | 0.66 | 0.62 | **0.79** | 0.30 | 0.55 | best coder in 8 GB |
| qwen3:14b ⚠ | 14B | ~8.7 GB | 0.88 | 0.85 | 0.80 | 0.81 | 0.80 | all-rounder + reasoning |
| qwen3:8b ⚠ | 8B | ~5 GB | **0.90** | **0.88** | 0.74 | 0.70 | 0.78 | best writer/general <14B |
| qwen3:4b ⚠ | 4B | ~3 GB | 0.84 | 0.80 | 0.60 | 0.45 | 0.72 | best in ≤4 GB / Spanish |
| qwen2.5:14b | 14B | ~8.7 GB | 0.83 | 0.80 | 0.70 | 0.31 | 0.62 | proven 14B writer |
| qwen2.5:7b | 7B | ~4.5 GB | 0.74 | 0.70 | 0.60 | 0.28 | 0.58 | battle-tested generalist |
| phi4:14b | 14B | ~8.7 GB | 0.80 | 0.72 | 0.66 | 0.75 | 0.55 | strong reasoner (no-think) |
| phi4-reasoning:14b ⚠ | 14B | ~8.7 GB | 0.78 | 0.65 | 0.70 | **0.99** | 0.50 | near-frontier reasoning |
| phi4-mini:3.8b | 3.8B | ~2.8 GB | 0.60 | 0.55 | 0.66 | 0.55 | 0.45 | code/reason for size |
| deepseek-r1:14b ⚠ | 14B | ~8.7 GB | 0.63 | 0.50 | 0.55 | **0.85** | 0.45 | math/reasoning |
| deepseek-r1:7b ⚠ | 7B | ~4.5 GB | 0.50 | 0.40 | 0.50 | 0.68 | 0.40 | reasoning in 8 GB |
| deepseek-r1:1.5b ⚠ | 1.5B | ~1.2 GB | 0.35 | 0.25 | 0.30 | 0.36 | 0.25 | only reasoner on 8 GB CPU |
| deepseek-coder-v2:16b | 16B MoE | ~9.5 GB | 0.55 | 0.45 | 0.71 | 0.40 | 0.45 | fast code (2.4B active) |
| aya-expanse:8b | 8B | ~5 GB | 0.55 | 0.70 | 0.35 | 0.30 | **0.85** | translation / multilingual |
| mistral-nemo:12b | 12B | ~7.5 GB | 0.65 | 0.62 | 0.45 | 0.30 | 0.68 | 128K ctx, ES summaries |
| gemma2:9b | 9B | ~5.5 GB | 0.75 | 0.72 | 0.43 | 0.10 | 0.68 | strong multilingual chat |
| llama3.1:8b | 8B | ~5 GB | 0.72 | 0.68 | 0.51 | 0.14 | 0.50 | general, RAG |
| llama3.2:3b | 3B | ~2 GB | 0.64 | 0.60 | 0.45 | 0.20 | 0.45 | concise general (8 GB CPU) |
| llama3.2:1b | 1B | ~0.8 GB | 0.45 | 0.40 | 0.30 | 0.10 | 0.30 | classify / extract / short |
| qwen2.5:0.5b | 0.5B | ~0.4 GB | 0.30 | 0.22 | 0.20 | 0.10 | 0.18 | trivial tasks only |

(Full list incl. 3B coders, mistral:7b, deepseek-coder:6.7b, gemma2:2b in `models_catalog.py`.)

## Machine tier → what to run, by axis

Largest practical (interactive) model in Q4_K_M per hardware class. The hard "does it fit" limit is
computed from VRAM/RAM by `profiler._max_params_q4`; this table adds the **per-axis** pick.
Footprint rule of thumb: `RAM ≈ params_B × 0.6 GB` (Q4_K_M) **+ KV-cache** (grows with context:
an 8B model adds ~1 GB at 8K, ~5 GB at 32K, ~20 GB at 128K).

| Machine tier | Max model | tok/s | code | writing | reasoning | multilingual |
|---|---|---|---|---|---|---|
| ≤8 GB RAM, no GPU | 3B | 5–10 | qwen2.5-coder:3b | qwen3:4b | deepseek-r1:1.5b | qwen2.5:3b |
| 16–32 GB RAM / Apple 16 GB | 7B | 8–22 | qwen2.5-coder:7b | qwen3:8b | deepseek-r1:7b | aya-expanse:8b |
| GPU 8–12 GB (3060/4070) | 8B | 25–52 | qwen2.5-coder:7b | qwen3:8b | qwen3:8b | aya-expanse:8b |
| GPU 24 GB+ / Apple 32–64 GB | 32B | 35–135 | qwen2.5-coder:32b | qwen2.5:14b | phi4-reasoning:14b | qwen3:14b |

Quantization sweet spot: **Q4_K_M** for chat/writing (≈+0.24 perplexity vs FP16, within noise on
most benchmarks); **Q5_K_M / Q6_K** for code/math/agentic where small errors compound; Q8/FP16 only
for research. Avoid ≤Q3 (10–20 pt drops on code). Interactive UX needs **>15 tok/s**.

### Sources
- Code: [Qwen2.5-Coder report](https://arxiv.org/html/2409.12186v3), [EvalPlus](https://evalplus.github.io/leaderboard.html), [BigCodeBench](https://bigcode-bench.github.io/), [LiveCodeBench](https://livecodebench.github.io/).
- General/writing/multilingual: [Qwen3 report](https://arxiv.org/abs/2505.09388), [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/), [Aya-Expanse](https://arxiv.org/abs/2412.04261), [Gemma 2](https://arxiv.org/html/2408.00118v1), [BenchMAX](https://arxiv.org/pdf/2502.07346), [La Leaderboard ES](https://arxiv.org/pdf/2507.00999), [IFEval/Arena-Hard](https://llm-stats.com/benchmarks/arena-hard).
- Reasoning: [DeepSeek-R1](https://arxiv.org/html/2501.12948v1), [Phi-4-reasoning](https://arxiv.org/pdf/2504.21318), [Phi-4-mini-reasoning](https://arxiv.org/pdf/2504.21233).
- Hardware: [llama.cpp quant eval](https://github.com/ggml-org/llama.cpp/discussions/2094), [KV-cache math](https://lyceum.technology/magazine/kv-cache-memory-calculation-llm/), [GPU inference benchmarks](https://github.com/XiongjieDai/GPU-Benchmarks-on-LLM-Inference).

hibrid runs a **startup micro-benchmark** to replace these estimates with the machine's real
tokens/sec, cached per node.

## Weight links

| Model | Hugging Face | Ollama |
|---|---|---|
| Llama 3.2 1B | huggingface.co/meta-llama/Llama-3.2-1B-Instruct | ollama.com/library/llama3.2 (`:1b`) |
| Llama 3.2 3B | huggingface.co/meta-llama/Llama-3.2-3B-Instruct | ollama.com/library/llama3.2 (`:3b`) |
| Qwen2.5 0.5B | huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF | ollama.com/library/qwen2.5 (`:0.5b`) |
| Qwen2.5 1.5B | huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF | ollama.com/library/qwen2.5 (`:1.5b`) |
| Qwen2.5 3B | huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF | ollama.com/library/qwen2.5 (`:3b`) |
| Qwen2.5-Coder 1.5B/7B | huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct | ollama.com/library/qwen2.5-coder |
| Gemma 2 2B | huggingface.co/google/gemma-2-2b-it | ollama.com/library/gemma2 (`:2b`) |
| Phi-3.5-mini | huggingface.co/microsoft/Phi-3.5-mini-instruct | ollama.com/library/phi3.5 |

## Where to store weights

- **Hugging Face** is the standard home for GGUF weights — Git LFS, built for multi-GB files,
  free CDN bandwidth. Default for everything.
- **GitHub** plain repos cap files at 100 MB; **GitHub Releases** allow up to 2 GB per asset with
  no total cap. Small quantized models that fit a Release: Qwen2.5-0.5B Q4 (~0.4–0.5 GB),
  Qwen2.5-1.5B (~1 GB), Llama 3.2 1B Q4 (~0.8 GB), Gemma 2 2B (~1.6 GB).
- **Never commit a GGUF into the git repo.** Keep canonical weights on Hugging Face; optionally
  mirror the smallest (Qwen2.5-0.5B Q4) as a GitHub Release for a zero-config first-run download.
