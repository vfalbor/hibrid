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
   them on a local model and spends a paid token only on the one final check that earns it.
   Tools can declare a task type (`"task_type": "loop_refine"`); if they don't, hibrid infers it.
3. **It guards your data.** Spot an email, a key, an ID in the prompt and the request is pinned
   to local — a rule, not a checkbox. Your text never reaches a third party.

It all runs behind one decision: `argmax U(d)` where
`U(d) = quality − λ_cost·cost − λ_lat·latency − λ_priv·privacy_risk`. The weights are knobs
you (or a tool) can set per request.

## Quickstart

```bash
pip install git+https://github.com/vfalbor/hibrid.git
cp .env.example .env        # add your cloud keys; point at a local runtime if you have one
hibrid serve                # OpenAI + Anthropic compatible, on :8095
curl localhost:8095/v1/node # see what it learned about your machine
```

A local runtime is optional but recommended — `ollama serve`, `llama-server`, or LM Studio.
All of them speak the OpenAI dialect, so hibrid talks to them the same way it talks to the cloud.

## Why nothing else does this

| | Cloud routers | Local apps | **hibrid** |
|---|:--:|:--:|:--:|
| Routes by task | ✅ | manual | ✅ |
| Knows your hardware | ❌ | hints | **measures it** |
| Local + cloud, automatic | ❌ | by hand | ✅ |
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

Day one, and honest about it. The decision engine is tested (`python tests/test_router.py`,
`tests/test_dialects.py`), the OpenAI and Anthropic endpoints work, the benchmark registry is
being seeded, and the confidence calibration sharpens with use. Streaming for the Anthropic
endpoint is the next item. Tell us where it breaks.

## Docs

- [`docs/INVESTIGACION.md`](docs/INVESTIGACION.md) — research behind the design (a 3-agent study)
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — architecture
- [`docs/EXECUTION_PROFILES.md`](docs/EXECUTION_PROFILES.md) — task-type routing & loop economics
- [`docs/PLAN.md`](docs/PLAN.md) — roadmap and community plan

## License

Apache-2.0. Part of the [tokenstree](https://tokenstree.eu) ecosystem.
