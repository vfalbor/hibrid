# hibrid — Competitive Comparison (internet research)

_Agent: CompetitorScan · Date: 2026-06-29 · All claims attributed; uncertain items marked._

## Comparison matrix

| Tool | Local-first | No API key for strong tier | Measures hardware | Routes by task axis | Open source | Published savings claim |
|---|---|---|---|---|---|---|
| **hibrid** | yes | **yes** (via authenticated agent CLI) | **yes** | yes (code/general/reasoning) | yes (Apache-2.0) | in progress (this study) |
| RouteLLM (LMSYS) | no | no | no | partial (strong/weak) | yes (Apache-2.0) | yes — ~85% MT Bench |
| LiteLLM (BerriAI) | partial | no | no | no | yes (MIT core) | no |
| OpenRouter | no | no | no | partial (Auto Router) | no | no |
| Martian | no | no | no | yes (perf prediction) | no | marketed, no number found |
| Not Diamond | no | no | no | yes (quality ranking) | partial | number not found |
| Unify.ai | no | no | no | yes | no | partial (benchmark suite) |
| semantic-router (Aurelio) | partial | n/a | no | yes (semantic) | yes (MIT) | latency only |
| Portkey AI Gateway | partial | no | no | no | yes (Apache-2.0) | no |
| GPTCache | partial | n/a (cache) | no | no | yes | yes — 30-70% via caching |
| LiteLLM+Ollama (DIY local-first) | yes | no | no | no (manual tiers) | yes | no |

Legend: "partial" = can use local models or do partial routing but not the design point; "n/a" = tool is not a model-caller (cache / decision layer).

## Positioning (honest)

hibrid's genuinely differentiated combination is two things no competitor researched does: (1) it reaches the **strong tier through the user's already-authenticated agent CLI/session** (`claude -p`, `codex`, `opencode`, `copilot`), so there is **no metered per-token API key** for frontier calls; and (2) it **benchmarks the actual machine at startup** (RAM/VRAM/tok-s) and routes on measured local latency rather than a spec sheet. Its other properties each exist somewhere in the field but are not bundled: the popular DIY LiteLLM+Ollama pattern is local-first but manual and still needs a cloud API key; RouteLLM, Unify, Not Diamond and Martian do learned quality/task routing but are cloud-API-centric and never measure your hardware; semantic-router and GPTCache attack latency and caching, not the local-vs-frontier money decision. **Where competitors are clearly stronger**, be candid: RouteLLM has peer-reviewed savings benchmarks (~85% on MT Bench at 95% GPT-4 quality) that hibrid has not yet matched; OpenRouter (400+ models) and Portkey (1600+ models) offer far broader provider coverage, observability, guardrails and enterprise hardening; and Martian (Accenture-backed, reportedly nearing a $1.3B valuation) and Not Diamond bring funding, scale and large proprietary evaluation datasets hibrid cannot match today.

## Competitors' advertised savings (with citations)

- **RouteLLM** — up to **~85% cost reduction on MT Bench** while keeping 95% of GPT-4 quality, with only ~14% of queries hitting the strong model; ~45% on MMLU, ~35% on GSM8K. Pairing: GPT-4 Turbo (strong) vs Mixtral 8x7B (weak). [LMSYS blog](https://www.lmsys.org/blog/2024-07-01-routellm/), [paper](https://arxiv.org/pdf/2406.18665)
- **GPTCache / semantic caching** — **~30-70% inference cost reduction** via reuse; 2-10x faster on cache hits; one study (GPT Semantic Cache) cut API calls **up to 68.8%** (hit rates 61.6-68.8%). [ACL paper](https://aclanthology.org/2023.nlposs-1.24/), [arxiv 2411.05276](https://arxiv.org/html/2411.05276v2)
- **FrugalGPT** — classic paper claim of **up to ~98% cost reduction** while matching the best single LLM (GPT-4) on some datasets; highly dataset-dependent, and LLMRouterBench (2026) reports it sometimes fails to beat the best single model. [arxiv 2305.05176](https://arxiv.org/pdf/2305.05176)
- **LLMRouterBench (2026)** — flagship routers (GraphRouter PF, Avengers-Pro) achieve **up to ~31.7-32% cost reduction with no accuracy loss**. [arxiv 2601.07206](https://arxiv.org/html/2601.07206v1)
- **Unify.ai** — claims its router beats individual endpoints on average across MT-Bench/MMLU/GSM8K/HellaSwag and cuts cost by using small models for simple tasks; no single headline % published. [overview](https://xnavi.ai/tools/unify)
- **Martian** — markets large cost reductions vs a single all-purpose model; **no first-party numeric benchmark located** (marked uncertain). [TechCrunch](https://techcrunch.com/2023/11/15/martians-tool-automatically-switches-between-llms-to-reduce-costs/), [VentureBeat](https://venturebeat.com/ai/why-accenture-and-martian-see-model-routing-as-key-to-enterprise-ai-success)
- **Not Diamond** — markets quality maximization plus cost/latency tradeoffs (`cost_quality_tradeoff` 0-10); **no specific savings % located** (marked uncertain). [docs](https://docs.notdiamond.ai/docs/quickstart)
- **OpenRouter / LiteLLM / Portkey** — no quality-routing savings %; their levers are cheapest-provider selection, self-hosting (no per-request fee), virtual keys and cost tracking. [OpenRouter](https://openrouter.ai/docs/guides/routing/routers/auto-router), [LiteLLM](https://docs.litellm.ai/docs/simple_proxy), [Portkey](https://portkey.ai/docs/product/ai-gateway)

## Field benchmarks to compare like-for-like

- **RouterBench** — benchmark for multi-LLM routing systems; establishes routing can save cost without quality loss. [arxiv 2403.12031](https://arxiv.org/html/2403.12031v2)
- **LLMRouterBench (2026)** — massive unified routing benchmark; up to ~32% cost cut at no accuracy loss for top routers. [arxiv 2601.07206](https://arxiv.org/html/2601.07206v1)
- **FrugalGPT** — cascade-with-quality-judge baseline; the ~98% headline. [arxiv 2305.05176](https://arxiv.org/pdf/2305.05176)
- **RouteLLM (MT Bench / MMLU / GSM8K)** — the most-cited strong/weak routing numbers. [LMSYS](https://www.lmsys.org/blog/2024-07-01-routellm/)

## Caveats

- Martian and Not Diamond advertise cost/quality gains but no first-party numeric savings benchmark was found in the sources searched — treat as marketing, not measured.
- FrugalGPT's ~98% is dataset-dependent and contested by the 2026 LLMRouterBench results.
- Several "partial" local-first tools (LiteLLM, Portkey, semantic-router, GPTCache) can use local models but are not local-first decision engines the way hibrid is.
- Context: Ollama v0.14 (Jan 2026) added direct Anthropic Messages API compatibility, making it easier for tools like Claude Code to call local models without a proxy — relevant to hibrid's niche.
