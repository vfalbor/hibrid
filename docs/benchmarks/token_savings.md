# hibrid token-savings study — what an agent session keeps off the paid tier

**Question.** Across a realistic agent session (mostly a refactor loop, plus a few hard one-shots),
how much of the work does hibrid keep on a *local* model, and how many frontier-tier tokens does
that avoid?

**Companion to** the [three-server throughput study](README.md). That one measured *how fast* local
models run and *what fraction of a task suite* each machine can solve at parity. This one measures
*token consumption avoided* across a single agent-shaped session, end to end, with the strong tier
actually wired in.

---

## TL;DR

On a two-core, 8GB, GPU-less box (`cpu_8gb`), a 16-call agent session routed through hibrid:

| Metric | Value |
|---|---|
| Calls kept local & free | **9 / 16 (56%)** |
| Frontier tokens **with** hibrid | 1,681 |
| Frontier tokens **without** hibrid (counterfactual: every call sent to frontier) | 2,882 |
| **Frontier tokens avoided** | **1,201 (42%)** |
| Refactor-loop calls that stayed local | **8 / 8** |

The whole code-refine loop stayed local; only the two genuinely hard reasoning prompts (plus most of
the light NLP) escalated — and those escalations went to a *cheap* frontier model, not the top of the
ladder.

---

## Method

- **Engine:** local hibrid at `http://127.0.0.1:8095`, node class `cpu_8gb`, local models
  `llama3.2:3b` and `qwen2.5-coder:1.5b` via the Ollama OpenAI-compatible endpoint.
- **Strong tier:** the user's Claude subscription via `cli:claude` (agent CLI). **No API key, no
  per-token meter.** Because there is no per-token dollar price, the saving is expressed as
  **frontier-tier tokens and calls avoided**, not dollars.
- **Workload (`token_savings_run.py`):** 16 calls shaped like a real agent session — 8 `loop_refine`
  (typo fix, comprehension, docstring, type hints, divide-by-zero guard, …), 4 `simple`
  (translate/classify/extract/summarize), 2 `general`, 2 `deep_reason` (queue backpressure design,
  the Ω(n log n) sorting proof). Models warmed first; transient 5xx retried once with backoff.
- **Token counts** come from each response's own `usage` block. The counterfactual "without hibrid"
  is the sum of every call's tokens as if all had been sent to the frontier.

Run it: `.venv/bin/python docs/benchmarks/token_savings_run.py` → writes `token_savings.json`.

---

## Results by task type

| Task type | Calls | Stayed local | Escalated | Tokens |
|---|---:|---:|---:|---:|
| `loop_refine` | 8 | 8 | 0 | 1,152 |
| `simple` | 4 | 1 | 3 | 270 |
| `general` | 2 | 0 | 2 | 243 |
| `deep_reason` | 2 | 0 | 2 | 1,217 |

The saving concentrates in the loop: it's the high-frequency part of a session, and it's where the
cheap-call-stays-local rule pays off most. The rarer, harder one-shots are the ones you actually
want a frontier model for.

Raw output: [`token_savings.json`](token_savings.json).

---

## Threats to validity

- **One session, 16 calls.** Indicative, not a leaderboard. The exact percentage depends on how
  loop-heavy your real session is — more loop, more local.
- **No dollar figure.** The strong tier is a flat-rate subscription via `cli:claude`; the honest unit
  is frontier tokens/calls avoided. Your dollar saving depends on what you'd otherwise pay per token.
- **CPU-only, ≤3B local models.** This is the floor. A GPU or Apple-silicon box runs larger local
  models and keeps even more off the paid tier.
- **Local models must be good enough.** The companion study showed a 0.5B model inventing email
  addresses; hibrid escalates rather than trusting a too-small model, which is why some light tasks
  here went to the cheap frontier tier instead of staying local.
