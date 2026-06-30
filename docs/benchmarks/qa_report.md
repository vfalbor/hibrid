# A Token-Zero QA Campaign for an LLM Router: Orchestrated Multi-Agent Testing and Repair of *hibrid*

**Authors:** hibrid project · orchestration by a project-manager agent with two worker agents
**Date:** 2026-06-30 · **Artifact:** `github.com/vfalbor/hibrid` @ `main` · **License:** Apache-2.0

---

## Abstract

We report a quality-assurance campaign on *hibrid*, an open-source router that decides, per call,
whether a task runs on a local open-weights model (free) or escalates to a paid frontier tier
reached through the user's own subscription (no API key). The campaign was designed under an
explicit cost constraint: **spend zero frontier tokens to find bugs.** We achieved this by testing
the routing *decision* directly — exercising the classifier and the `argmax`-utility router across
132 synthetic cases over four machine profiles — and by validating end-to-end serving with a
local-only inference subset (free). The work was executed as a small multi-agent organisation: one
orchestrator (project manager) and two worker agents operating on disjoint files under test-driven
development. The campaign surfaced **four genuine defects**, two of them critical model-mis-scoring
bugs, all fixed and regression-tested. The final test corpus is **197 passing assertions** with
zero failures. Total frontier-token cost of the *testing* phase was **zero**; the only token
expenditure was the bounded repair work, run on a cheaper model tier.

---

## 1. Introduction

LLM routers promise cost reduction by keeping cheap, high-volume work on small local models and
reserving expensive models for the calls that need them. The obvious way to test such a system —
issue hundreds of prompts and inspect the answers — is self-defeating: it spends the very tokens
the router exists to save, and conflates two questions (*did it route correctly?* and *was the
model's answer good?*). We separate them. Routing correctness is a property of a pure decision
function and can be checked exhaustively for free; answer quality is a separate, sampled concern.

This report documents (i) the test design, (ii) the multi-agent execution model, (iii) the defects
found and the fixes, and (iv) threats to validity.

## 2. System under test

*hibrid* makes a pre-execution decision `d* = argmax_d U(d)` over candidate destinations
`{local_free, paid_cheap, paid_strong}`, where

```
U(d) = quality(d) − λ_cost·cost(d) − λ_lat·latency(d) − λ_priv·privacy_risk(d)
```

subject to hard overrides (PII → local; `allow_cloud=false` → local; `force=X` → X). The decision
draws on two application-level tables introduced earlier in the project:

- a **five-axis** task→model mapping (`general`, `writing`, `code`, `reasoning`, `multilingual`),
  with per-axis capability priors for a curated catalogue of small models, grounded in public
  benchmarks; and
- a **machine-tier taxonomy** (`cpu_small` → `gpu_24gb+`) bounding which models fit a node.

The unit of testing is therefore the function `router.decide(node, features, options)` plus the
upstream `classifier.classify(messages)`.

## 3. Methodology

### 3.1 Token-zero test design

The campaign has two layers:

1. **Decision-level battery (132 cases, 0 inference).** A harness (`tests/batch_qa.py`) constructs
   four realistic `NodeProfile`s (`cpu_small`, `cpu_large`, `gpu_12gb`, `gpu_24gb`) with the model
   sets each tier would plausibly hold, and asserts invariants across eleven categories:
   classifier labelling, axis mapping, PII override, offline mode, forced destination, tier caps
   (loops/`simple`/`translate`/`batch` never reach `paid_strong`), per-axis model selection,
   machine-fit, edge cases (no local / no cloud / neither / empty / very long input), and
   interactive latency weighting. No model is invoked; cost is zero.

2. **Live serving subset (local-only, free).** A handful of real calls to the running engine
   (`POST /v1/chat/completions`, `allow_cloud=false`) confirm the service returns non-empty content
   on `tier=local_free`. This uses local inference only — no frontier tokens.

### 3.2 Multi-agent execution model

The repair work followed an orchestrator/worker pattern (the same orchestration idea the router
itself supports for skills):

| Role | Agent | Remit |
|---|---|---|
| Orchestrator (PM) | this session | design harness, run battery, triage, review diffs, commit |
| Worker A | Sonnet | `backend/classifier.py` + `tests/test_classifier.py` |
| Worker B | Sonnet | `backend/router.py`, `models_catalog.py`, `profiles.py` + `tests/test_router_edge.py` |

Workers were assigned **disjoint files** to avoid write contention, told to use **TDD** (failing
test first), to keep changes minimal, and to keep every pre-existing suite green. The orchestrator
verified the union of changes, not each in isolation. Worker agents ran on a cheaper model tier to
bound cost — the same local-first economic logic the system under test embodies.

## 4. Results

### 4.1 Decision battery

All 132 decision-level assertions pass after repair. Distribution by category:

| Category | Pass | What it guards |
|---|---:|---|
| classifier | 16 | task-type labelling incl. write/translate/code/deep_reason |
| axis | 11 | task_type → axis mapping (5 axes) |
| pii | 24 | PII forces local across all tiers |
| offline | 16 | `allow_cloud=false` never leaves the box |
| force | 12 | forced destination honoured |
| cap_cheap | 12 | simple/translate/batch never hit `paid_strong` |
| cap_loop | 4 | loop_refine never hits `paid_strong` |
| axis_pick | 16 | chosen local model is best-on-axis among those that fit |
| fit | 12 | chosen model fits the node's parameter budget |
| edge | 5 | no-local / no-cloud / neither / empty / long input |
| interactive | 2 | slow local penalised; fast local preferred |
| **Total** | **132** | (machine-readable: `docs/benchmarks/qa_batch_results.json`) |

### 4.2 Live serving subset

6/6 prompts returned non-empty content on `tier=local_free` (e.g. classification 12.5 s, translation
2.6 s, a trivial factual query 1.0 s) on the worst available box (8 GB, no GPU, `llama3.2:3b` at
~6 t/s measured). After deploying the fixes, a re-check on the restarted engine reproduced
`local_free` serving.

### 4.3 Aggregate test corpus

| Suite | Assertions | Status |
|---|---:|---|
| `test_router.py` | 15 | pass |
| `test_classifier.py` (new) | 12 | pass |
| `test_router_edge.py` (new) | 34 | pass |
| `test_dialects.py` | 4 | pass |
| `batch_qa.py` (new) | 132 | pass |
| **Total** | **197** | **0 failures** |

### 4.4 Cost

The defect-finding phase cost **0 frontier tokens** (pure-function checks + local inference).
Token spend was confined to the two worker agents performing repairs, both on a cheaper tier
(≈31k and ≈90k subagent tokens respectively) — a deliberate inversion of the usual "burn frontier
tokens to test" approach.

## 5. Defects found and fixes

| # | Severity | Component | Failure scenario | Fix |
|---|---|---|---|---|
| 1 | High | `classifier._infer_task_type` | A text-only hard-reasoning prompt ("design the architecture… reason the trade-offs… prove the complexity") scored ~0.32 complexity and fell through to `general`, so a genuinely hard task would not escalate. | Treat ≥3 distinct hard-reasoning signals as `deep_reason` even without code and below the length-complexity threshold. |
| 2 | Critical | `models_catalog.match` | `match("llama3.2:1b")` returned the `llama3.2:3b` entry (substring collision: "3" of "3b" appears in "llama3.2"), so a 1B model inherited a 3B's capability scores — inflating the router's quality estimate for a weaker model. | Anchor matching: family must be an exact `family:` prefix, and the size check is anchored to the text after the colon. |
| 3 | Critical | `models_catalog.match` | `match("phi4-reasoning:14b")` returned the plain `phi4:14b` entry (prefix substring), so the reasoning specialist was scored 0.75 instead of 0.99 and never preferred for reasoning. | Same anchored-prefix fix. |
| 4 | Minor | `router.decide` | When a forced kind was unavailable, the router correctly fell back but reported `"forced by client to cloud_strong"`, misstating what ran. | Reason string now explains the fallback honestly. |

Negative results (investigated, found sound): `_params_in` parsing of decimal sizes and quant
suffixes; `qwen2.5` vs `qwen2.5-coder` disambiguation; `best_local_for`/`best_orchestrated_for`
tie-breaking and empty pools; `tier_for` boundary values; utility scaling. We note `task_policy.paid_cap`
is currently dead documentation — enforcement is via `ExecutionProfile.tier_order`, which is
consistent with it — flagged for future consolidation.

## 6. Threats to validity

- **Construct validity.** Decision-level tests assert *routing*, not answer quality; a correct
  route to a weak model can still yield a weak answer. Capability priors are benchmark-derived
  estimates, not per-node measurements (the engine refines them online with real history).
- **External validity.** The live subset ran on one CPU-only node with small models; throughput and
  the local/escalate split differ on GPU or Apple-silicon nodes.
- **Pre-execution blindness.** The router decides before seeing the output, so it cannot yet catch a
  confidently-wrong local answer — a known limitation, consistent with an earlier blind-judged study
  (local 0.81 vs frontier 0.91; ~89% of quality retained). An output-aware escalation signal remains
  future work.
- **Synthetic prompts.** Classifier cases are hand-written; real traffic will include adversarial
  phrasings not covered here.

## 7. Conclusion

Testing an LLM router by metering its decision function — rather than its generations — let us run a
132-case campaign at zero frontier-token cost and still uncover four real defects, two of them
capability-mis-scoring bugs that silently degraded routing quality. Organising the repair as a
small orchestrator/worker agent team on disjoint files under TDD kept the changes surgical and the
suite green (197/0). The result is both a hardened router and a reusable, cost-honest QA harness
(`tests/batch_qa.py`) that any contributor can extend without spending a frontier token to do so.

## Reproducibility

```bash
git clone https://github.com/vfalbor/hibrid && cd hibrid
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python tests/test_router.py        # 15/15
.venv/bin/python tests/test_classifier.py    # 12/12
.venv/bin/python tests/test_router_edge.py   # 34/34
.venv/bin/python tests/batch_qa.py           # 132, 0 failures  (token-zero)
.venv/bin/python tests/batch_qa.py --live    # + local-only serving subset (free)
```

Raw machine-readable results: `docs/benchmarks/qa_batch_results.json`.
