# hibrid

**One router under all your AI tools. Keep the tools — cut the bill.**

![License](https://img.shields.io/badge/license-Apache--2.0-176043)
![Status](https://img.shields.io/badge/status-alpha%20·%20live-c2691c)
![API](https://img.shields.io/badge/API-OpenAI%20%2B%20Anthropic-3b5b8c)

hibrid slides underneath Claude Code, Gemini CLI, aider and Copilot and quietly sends
each call to the cheapest model that can actually do the job — Opus when it matters,
Haiku when it's plenty, and a model on **your own machine** for everything in between.

Your tools don't change. Your token bill does. And anything private stays on your box.

> Live demo: **[hibrid.tokenstree.eu](https://hibrid.tokenstree.eu)** · Launch story:
> [tokenstree.eu/newsletter](https://tokenstree.eu/newsletter/2026-06-26-hibrid-router-that-knows-your-machine.html)

---

## The problem

You point a coding agent at Opus and let it run. It writes, runs the tests, fails, fixes,
runs again — fifty rounds, every one billed at frontier prices. Most of those rounds didn't
need a frontier model. A small model on the machine in front of you would have handled them.
They went to the cloud anyway, because your tooling can't tell "fix this typo" from
"redesign this module."

hibrid is the missing layer that can.

## Drop it under the tools you already use

hibrid speaks both the **OpenAI** and the **Anthropic** dialect, so you point a tool's base
URL at it and nothing else moves:

```bash
# Claude Code  (Anthropic API)
export ANTHROPIC_BASE_URL=https://hibrid.tokenstree.eu
claude

# aider / Copilot-style tools  (OpenAI API)
export OPENAI_BASE_URL=https://hibrid.tokenstree.eu/v1
aider

# anything with an OpenAI-compatible mode (Gemini CLI, etc.) points here too
```

Underneath, hibrid moves the request across Opus → Haiku → a local model by task type —
transparently. Every response carries a small `hibrid` block telling you where it actually ran.

## How it decides

1. **It measures your machine.** On startup it detects RAM, VRAM and chip, then runs a
   micro-benchmark that times the *real* tokens/sec of your local models. It doesn't guess
   from a spec sheet — it times your hardware. No other router does this.
2. **It keeps loops local.** A refine-and-retest loop is hundreds of cheap calls. hibrid runs
   them on a local model and spends a strong call only on the one final check that earns it.
   Tools can declare a task type (`"task_type": "loop_refine"`); if they don't, hibrid infers it.
3. **No API keys.** For anything beyond the local model, hibrid delegates to an orchestration
   layer you're *already* signed into — a headless agent CLI (`claude -p`, `codex exec`,
   `opencode run`, `copilot`), a local skills service, or your harness's own session — and picks
   whichever is available and fastest. Your subscription, not a pay-per-token key. See
   [docs/ORCHESTRATION.md](docs/ORCHESTRATION.md).
4. **It guards your data.** Spot an email, a key, an ID in the prompt and the request is pinned
   to local — a rule, not a checkbox. Your text never reaches a third party.

It all runs behind one decision: `argmax U(d)` where
`U(d) = quality − λ_cost·cost − λ_lat·latency − λ_priv·privacy_risk`. The weights are knobs
you (or a tool) can set per request.

## Quickstart

```bash
pip install git+https://github.com/vfalbor/hibrid.git
hibrid serve                  # OpenAI + Anthropic compatible, on :8095
curl localhost:8095/v1/node   # what it learned about your machine + which backends it found
curl localhost:8095/v1/policy # the task → LLM matrix it routes by
```

No keys to configure. hibrid discovers what's already on your machine:
- a **local runtime** (`ollama serve`, `llama-server`, or LM Studio) for the local tier — optional
  but recommended; they all speak the OpenAI dialect.
- an **orchestration backend** for the strong tier — any logged-in agent CLI
  (`claude` / `codex` / `opencode` / `copilot`), a skills service (`HIBRID_SKILLS_URL`), or a
  harness session token. Whatever is present, hibrid uses adaptively.

## Use it from your agent — the `/hibrid` skill

If your agent supports skills (e.g. Claude Code), this repo ships a `/hibrid` skill that delegates a
task — or a cheap sub-task — to the local engine instead of spending frontier tokens. The agent stays
the brain; hibrid is the muscle for cheap work.

```bash
ln -sfn "$(pwd)/skills/hibrid" ~/.claude/skills/hibrid   # install (repo stays the source of truth)
```

Then `/hibrid <task>` routes the task and reports where it ran. It composes with expertise skills —
`/josecela`, `/viral`, `/senior-dev` and the like: their framework shapes the prompt, hibrid routes
the execution (mechanical sub-steps stay local/free; frontier-grade generation goes to the strong
tier). See [`skills/`](skills/).

## Why nothing else does this

| | Cloud routers | Local apps | **hibrid** |
|---|:--:|:--:|:--:|
| Routes by task | ✅ | manual | ✅ |
| Knows your hardware | ❌ | hints | **measures it** |
| Local + strong, automatic | ❌ | by hand | ✅ |
| Strong tier with **no API key** | ❌ | ❌ | **your subscription, via your agent** |
| Private data stays local | ❌ | partial | **enforced** |
| Sits under your existing tools | some | ❌ | ✅ |

The crossing of those rows lived only in research papers until now. hibrid ships it.

## It belongs to the community

hibrid routes better when it knows what each machine runs — and you know that, not us. The core
piece is a shared benchmark registry: install hibrid, it measures your machine, and (if you opt
in) you share the result — hardware and speed only, never your prompts. The next person with a
laptop like yours routes well from minute one.

The easiest, most useful contribution is **your machine's benchmark**. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Day one, and honest about it. The decision engine is tested (31 passing tests), the OpenAI and
Anthropic endpoints work, the no-API-key orchestration layer is in, and a first
[benchmark study](docs/benchmarks/) on three real CPU servers shows local models handling
43–100 % of a task suite at parity (the fraction set by the machine). Streaming for the Anthropic
endpoint is the next item. Tell us where it breaks.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the layers fit together
- [`docs/ORCHESTRATION.md`](docs/ORCHESTRATION.md) — the task→LLM matrix & no-API-key backends
- [`docs/EXECUTION_PROFILES.md`](docs/EXECUTION_PROFILES.md) — task-type routing & loop economics
- [`docs/MODELS.md`](docs/MODELS.md) — the curated local-model catalog & task-axis matching
- [`docs/RESEARCH.md`](docs/RESEARCH.md) — research behind the design (a 3-agent study)
- [`skills/`](skills/) — the `/hibrid` agent skill (route tasks through the local router; composes with other skills)
- [`docs/benchmarks/`](docs/benchmarks/) — **benchmark studies**: three-server local routing, plus a [3-agent verification study](docs/benchmarks/study2/) (tokens, LLM-judged quality, competitive comparison)
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — phases, the hub, and the community flywheel
- [`docs/PLAN.md`](docs/PLAN.md) — deep community & hosting plan ([Spanish original](docs/PLAN.es.md))

## License

Apache-2.0. Part of the [tokenstree](https://tokenstree.eu) ecosystem.
