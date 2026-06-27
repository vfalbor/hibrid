# hibrid — model / machine mapping

hibrid doesn't pick a local model by "does it fit in memory" alone. It keeps a curated catalog
of small models known to perform acceptably, scored per task axis (general / code / reasoning),
and combines that with the machine's measured speed. The mapping lives in
`backend/models_catalog.py`; routing picks the best **available** model that fits the machine and
is competent for the detected task.

## Curated small models

Capability scores (0–1) are priors from public benchmarks/reputation (HF leaderboards, code
evals, family reputation) and are refined by the node's own history.

| Model | Params | ~RAM (Q4) | general | code | reasoning | Good for |
|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | 7B | ~5 GB | 0.72 | **0.82** | 0.66 | serious code |
| qwen2.5:7b | 7B | ~5 GB | **0.76** | 0.70 | 0.68 | strong generalist |
| llama3.1:8b | 8B | ~5.5 GB | 0.75 | 0.62 | 0.68 | general, RAG |
| phi3.5:3.8b | 3.8B | ~2.6 GB | 0.66 | 0.55 | **0.70** | reasoning for its size |
| qwen2.5:3b | 3B | ~2.2 GB | 0.66 | 0.60 | 0.56 | balanced small |
| llama3.2:3b | 3B | ~2 GB | 0.62 | 0.45 | 0.48 | concise general |
| gemma2:2b | 2B | ~1.7 GB | 0.58 | 0.40 | 0.46 | light general |
| qwen2.5-coder:1.5b | 1.5B | ~1.1 GB | 0.56 | 0.66 | 0.46 | code, tiny |
| qwen2.5:1.5b | 1.5B | ~1 GB | 0.55 | 0.50 | 0.45 | fast all-rounder |
| llama3.2:1b | 1B | ~1.3 GB | 0.45 | 0.30 | 0.30 | classify / extract / short |
| qwen2.5:0.5b | 0.5B | ~0.6 GB | 0.38 | 0.30 | 0.28 | very short tasks only |

Task → axis: code or detected code → `code`; deep reasoning → `reasoning`; otherwise `general`.

## Machine class → what to run

| Machine | Recommended local | Notes |
|---|---|---|
| CPU, 8 GB RAM | 1–3B Q4 (qwen2.5:1.5b, llama3.2:3b) | classify/extract/short; ~10–19 tok/s (measured) |
| CPU, 16 GB RAM | 7B Q4 | summaries, RAG, simple code |
| GPU 8 GB | 7–8B Q4 | most tasks, 40–60 tok/s |
| GPU 12–16 GB | 13–14B Q4 | mid reasoning, agents |
| GPU 24 GB | 14–34B Q4 | strong code/reasoning |
| Apple Silicon 64 GB+ | up to 70B Q4 | unique: holds models no consumer GPU can |

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
