# hibrid — research, benchmarks and conclusions

This document records the evidence hibrid's design rests on: the routing literature, the
local-inference landscape, the market gap, and a set of measured benchmarks run on real
hardware.

---

## 1. What hibrid is

A transparent router that sits under existing AI tools (Claude Code, Gemini CLI, aider,
Copilot) and sends each call to the cheapest model that can do the job — a strong model when
it matters, a model on the user's own machine for everything in between — based on:

- the machine's real capabilities (RAM, VRAM, chip, measured tokens/sec),
- the models the user can reach (local runtimes + an orchestration backend — an agent CLI,
  a skills service or harness passthrough — reached through the user's existing subscription,
  no API key),
- the task type and complexity,
- cost, latency and privacy.

It speaks the OpenAI and Anthropic dialects, so adopting it is changing a base URL.

---

## 2. Routing literature (design basis)

- **Predictive routing.** A light classifier predicts whether a small/local model will match
  the cloud answer, with a tunable quality knob (Hybrid LLM, ICLR 2024; RouteLLM, 2024). hibrid
  maps that knob to per-user cost/privacy weights.
- **Cascades with verification.** Run the small model, measure calibrated confidence, escalate
  only when needed (FrugalGPT 2023; AutoMix, NeurIPS 2024; Tabi, EuroSys 2023). Raw confidence
  is poorly calibrated and must be corrected (Platt/isotonic).
- **Cheap decision signals.** Query features (length, language, code, PII) → embedding+kNN over
  history (kNN rivals learned routers, 2025) → calibrated local confidence.
- **Unified utility.** `U(d) = quality − λ_cost·cost − λ_lat·latency − λ_priv·privacy_risk`,
  pick `argmax`. The escalation threshold is derived, not hand-set.
- **Evaluation.** RouterBench / RouterEval. Headline KPI: share of queries solved locally at
  parity quality.

Key references: arXiv 2404.14618, 2406.18665, 2305.05176, 2310.12963, 2211.17192, 2403.12031.

---

## 3. Local inference landscape

- **Runtimes.** Ollama (laptops/desktops), llama.cpp (edge/CPU/AMD/Intel), vLLM (GPU servers).
  All expose an OpenAI-compatible API, so switching local↔cloud is a URL change.
- **Quantization.** Q4_K_M is the reference (<2% quality loss). Memory rule of thumb:
  `GB ≈ params_B × 0.65` for Q4, plus 1–2 GB KV-cache.
- **Capability matters, not just fit.** A 1B model fits almost anywhere but isn't good at code.
  hibrid keeps a curated model→capability table (see [MODELS.md](MODELS.md)) so the model/machine
  mapping favours models known to perform acceptably for the task, then measures their real speed
  with a startup micro-benchmark.

---

## 4. Market gap

Cloud routers (OpenRouter, RouteLLM, LiteLLM, Portkey) route between paid models but ignore the
user's hardware. Local apps (Ollama, LM Studio, aider, Continue, Cline) can run local but leave
the local↔cloud decision to the user. Token-savers like caveman-code only shrink the size of a
cloud call rather than removing it. hibrid owns the loop **and** makes the routing decision,
local-first — the crossing that previously lived only in research.

---

## 5. Measured benchmarks

Run on a representative low-end box (4 vCPU, ~7.9 GB RAM, no GPU, Ubuntu 24.04) via Ollama's
OpenAI-compatible API. Fixed agentic code-fix task, temperature 0, max_tokens 200, median of
3 runs (cold-load run excluded).

| Model | Params | Median tok/s | Median latency | Tokens/call | Fixed the bug? |
|---|---|---|---|---|---|
| qwen2.5:1.5b | 1.5B | **18.9** | **2.4 s** | 46 | ✅ cleanest minimal fix |
| llama3.2:1b | 1B | 17.7 | — | 200 (verbose) | ✅ correct logic |
| llama3.2:3b | 3B | 10.2 | 7.7 s | 78 | ✅ concise |

All three solved the task correctly on a CPU-only machine. On this hardware qwen2.5:1.5b is the
throughput/latency winner; llama3.2:3b is the most concise.

### Loop economics (the core scenario)

A 50-round refinement loop run entirely on local llama3.2:3b: **3,900 output tokens, ~6.3 minutes,
$0.00**. The same 50-round loop (assuming ~500K input / 75K output total) on cloud models:

| Where the loop runs | Cost |
|---|---|
| Local (hibrid, this box) | **$0.00** |
| Claude Haiku 4.5 | ≈ $0.88 |
| GPT-4o | ≈ $2.00 |
| Claude Opus 4.8 | ≈ $4.38 |

Cloud pricing ($/1M output tokens): Opus 4.8 $25, GPT-4o $10, Haiku 4.5 $5, GPT-4o-mini $0.60
(official pricing pages, June 2026).

---

## 6. Conclusions

1. **Small local models clear real agentic sub-tasks.** A 1.5B model fixed a code bug correctly
   at ~19 tok/s on a CPU-only box — fast enough to be useful, free to run.
2. **The loop is where money leaks.** Keeping a 50-round loop local saves roughly $0.9–$4.4 per
   loop versus cloud, with the expensive model reserved for the final check.
3. **Capability-aware mapping beats size-only.** Routing a code task to a code-competent small
   model (e.g. qwen2.5-coder) matters more than raw parameter count.
4. **Start simple.** kNN over history + calibrated confidence + a utility function covers the
   four factors without training. Calibration quality is the main risk to the KPI.

See [MODELS.md](MODELS.md) for the curated model/machine mapping and weight links, and
[EXECUTION_PROFILES.md](EXECUTION_PROFILES.md) for how task type drives routing.
