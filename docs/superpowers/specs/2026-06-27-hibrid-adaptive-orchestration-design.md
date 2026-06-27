# hibrid — adaptive orchestration design (no-API-key strong tier)

Date: 2026-06-27 · Status: approved, in implementation

## Problem

hibrid routes a request to the cheapest destination that can do the job. The local side is
solid (axis-aware model selection on the user's machine). The **non-local side was wrong for
this project**: it assumed a raw `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` and one hardcoded model
per tier. Two issues:

1. **No API keys.** hibrid must reach stronger capability through the orchestration layer it
   already sits under — the user's *already-authenticated* coding agent (Claude Code, Codex,
   opencode, Copilot) in headless mode, or a skills-orchestrator service, or pass-through of the
   harness's own session — never a pay-per-token key the user has to provision.
2. **No explicit task → LLM mapping.** "Which model for which task type" was scattered across
   classifier → profiles → catalog → config. It needs to be one readable, auditable policy.

## Design

### Destinations: tiers + pluggable backends

Tiers (capability/cost ladder): `local_free` → `agent_cheap` → `agent_strong`.

A **Backend** is *how* a non-local tier executes. One interface, three mechanisms; the system is
**adaptive** — it discovers what's available and picks the best at the moment:

- `CliBackend(agent)` — shells out to a headless agent: `claude -p`, `codex exec`,
  `opencode run`, `copilot`. Uses the user's existing subscription. No key.
- `ServiceBackend(url)` — a local skills-orchestrator service exposing one endpoint; it owns auth
  and orchestrates agents underneath.
- `PassthroughBackend()` — forwards upstream reusing the harness's own session token.

### Backend discovery (mirrors the local micro-benchmark)

At startup hibrid probes: which agent CLIs are installed and logged in (a tiny health prompt),
which service endpoints answer, whether passthrough auth is present. It builds a **backend
registry** with, per backend, the tiers/models it can serve and a measured latency/health score.
Cached; re-probed lazily.

### task_policy.py — the explicit matrix (the missing piece)

| task_type | tier ladder | axis | per-tier model preference |
|---|---|---|---|
| loop_refine | local_free, agent_cheap | code | local: coder model; agent: cheap coder; never agent_strong per-iteration |
| loop_verify | agent_strong, agent_cheap, local_free | code | strongest available code model (final check only) |
| deep_reason | agent_strong, local_free, agent_cheap | reasoning | strongest reasoning model |
| simple | local_free, agent_cheap | general | local small general; agent cheap |
| interactive | local_free, agent_cheap, agent_strong | general | latency-weighted |
| batch | local_free, agent_cheap | general | maximize local |
| general | full ladder | general | pure utility |

`profiles.py` keeps the tier ladder + λ overrides + escalation policy; `task_policy` adds the
**axis** per task type and the **per-tier model pick** for both local and orchestrated tiers.

### Per-axis capability tables

- Local models: already in `models_catalog.py` ({general, code, reasoning} caps per model).
- Orchestrated models: a parallel curated table (opus, sonnet, haiku, gpt-4o, gpt-4o-mini, the
  default models reachable via codex/opencode/copilot) with the same axis caps + a relative cost
  weight. This is what lets a tier pick the *best* backend-model for the task axis.

### Adaptive selection

Non-local candidates = every available `(backend, model)` serving the chosen tier. Each scored by
the existing utility `U(d) = quality − λcost·cost − λlat·latency − λpriv·privacy_risk`, with
quality from the axis table and latency from the backend's measured health. `argmax` ⇒ best
available now; if the preferred backend is down/unauthed the next falls in automatically.

## Benchmark (no keys)

- **Local tier:** real ollama inference on all three servers (tokenstree.com/.es/.eu, 4-core CPU,
  8 GB, no GPU). Models sized per box (.com ~0.5–1 B, .es/.eu up to 3–7 B Q4). Measure real tok/s
  and task quality.
- **Strong/cheap tier:** reached through the already-authenticated orchestration layer
  (`CliBackend` → Claude Code headless here). No API key — the production mechanism.
- **Tasks:** code-refactor loop, bugfix, classify/extract, translate, summarize, deep-reason.
- **Output:** scientific report (methodology, tables, matplotlib charts, analysis, threats to
  validity) under `docs/benchmarks/`, summarized to GitHub.

## Out of scope (YAGNI for now)

- Building the full skills-orchestrator service (we ship the `ServiceBackend` interface + a stub;
  CLI backends are the primary path).
- The community hub endpoints (separate spec, Phase 2 of ROADMAP).

## Testing

Unit tests: `task_policy` resolution, orchestrated axis table, backend discovery (mocked
subprocess), adaptive selection with backends up/down, and the existing router invariants.
