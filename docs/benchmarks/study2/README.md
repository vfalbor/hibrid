# hibrid study 2 — does it actually work? (tokens, quality, competition)

A three-agent study verifying the **hibrid** router on a CPU-only 8GB box (`cpu_8gb`,
2 cores, local models `llama3.2:3b` + `qwen2.5-coder:1.5b`, strong tier via `cli:claude`,
no API key). Every number is a real measured call against the live engine. Three independent
agents proposed and ran their own tests; a fourth measurement (LLM-judged quality) was added
on the user's request.

## 1. Token savings — agent "TokenBench"
Real before/after: each task run WITH hibrid (auto) and WITHOUT (`force:cloud_strong`, i.e. every
call to the frontier). 31 calls across 3 workloads.

- **74.2% of calls kept local**; **frontier tokens 1,069 with vs 8,531 without → 87.5% avoided.**
- Refactor loop (12 calls): **100% local, 100% avoided.**
- Reasoning workload (9 calls): **100% local, 100% avoided** (on this box).
- Mixed agent session (10 calls): 61% avoided.
- Correctness: loop_refine 14/14 local; PII (`simple`) stayed local. Data: `agent1_tokenbench.json`.

## 2. Answer quality — LLM-judged (`quality_judge.py`)
8 tasks, each answered AUTO and STRONG; an impartial frontier judge scored both 0–1, blind to source.

- **Mean local/auto quality 0.81 vs frontier 0.91 → ~89% of frontier quality retained.**
- **Parity rate 75%** (≥0.7, and within 0.1 of frontier).
- Gaps: one code fix (0.5 vs 1.0) and the Ω(n log n) proof (0.5 vs 0.9) — the hard items a 1–3B model
  is weakest on, and what a smarter output-aware escalation should catch. Data: `quality_judge.json`,
  `quality_judge.md`.

## 3. Routing correctness — agent "QualityGuard"
12-rule probe matrix: **11/12 PASS.**

- All **hard overrides correct**: PII→local even on `deep_reason`; `allow_cloud=false`→local;
  `force` local/cheap/strong honored; `loop_refine` never jumps to strong; `deep_reason` may escalate.
- One **soft** miss: under load, `simple` routed to the cheap paid tier (haiku) rather than local —
  never to the expensive frontier. Plus a field review (FrugalGPT, Hybrid LLM ICLR 2024, RouterBench).
  Data: `agent3_qualityguard.{json,md}`.

## 4. Competitive comparison — agent "CompetitorScan" (internet research)
Matrix vs RouteLLM, LiteLLM, OpenRouter, Martian, Not Diamond, Unify, semantic-router, Portkey,
GPTCache, DIY LiteLLM+Ollama.

- hibrid's differentiated combo: **local-first + no-API-key (auth'd agent CLI) + measures the machine**.
- Honest gaps: RouteLLM has peer-reviewed savings (~85% MT-Bench at 95% GPT-4 quality) hibrid hasn't
  matched; OpenRouter/Portkey have far broader coverage and enterprise hardening; Martian/Not Diamond
  have funding + large eval datasets. Field numbers: RouteLLM ~85%, FrugalGPT ~98% (contested),
  LLMRouterBench 2026 ~32% at no accuracy loss, semantic caching 30–70%. Data:
  `agent2_competitors.{json,md}`.

## Caveats (apply to the whole study)
- Small n, single LLM judge, short objective tasks — indicative, not a leaderboard.
- CPU-only ≤3B local models — the floor; a GPU/Apple-silicon box raises local coverage and quality.
- Strong tier is a flat-rate subscription (no per-token price) → savings are **frontier tokens/calls
  avoided**, not dollars.
- The router escalates on pre-execution features, not on whether the local answer was actually good —
  it can't yet catch a confidently-wrong local answer (the two quality gaps above).
- Routing of borderline classes (simple/deep_reason) shifts with measured latency/load.
