# hibrid — roadmap

hibrid is two halves. The **engine** runs on your machine (open-source, no account, prompts
never leave the box). The **hub** at `hibrid.tokenstree.eu` runs no inference at all — it only
aggregates opt-in, anonymous `(machine, model, quant, tok/s)` benchmarks and shares routing
policies, so the next person with a laptop like yours routes well from minute one. The roadmap
below moves from the engine that exists today to the community service that makes routing
better for everyone.

Legend: ✅ done · ⬜ planned.

## Phase 0 — Consolidate the engine *(almost done)*

- ✅ Engine scaffold: utility router, micro-benchmark profiler, escalation cascade, online
  confidence calibration.
- ✅ Execution profiles — task-type routing, loops stay local-first (`docs/EXECUTION_PROFILES.md`).
- ✅ AI-agnostic: both the **OpenAI** and **Anthropic** dialects, so any tool points its base URL
  at hibrid unchanged.
- ✅ Curated model catalog — pick the best *available* local model **for the task axis**
  (code/reasoning/general), not just the one with the most parameters (`docs/MODELS.md`).
- ✅ Tests green (`tests/test_router.py`, `tests/test_dialects.py`) and CI on every PR.
- ⬜ Packaging: publish to PyPI and Docker Hub so `pip install hibrid && hibrid serve` is one line.
- ⬜ **Streaming SSE** for the Anthropic endpoint — the one gap real coding agents need for a
  fully transparent drop-in. *Next item.*

## Phase 1 — Router quality

- ⬜ **kNN router** over the machine's own history — routing sharpens with use.
- ⬜ Evaluate against **RouterBench / RouterEval** to publish the headline KPI: *% of work
  resolved locally at parity*. This is the number that earns technical credibility.
- ⬜ Harden the **confidence calibration** — the #1 technical risk the research team flagged;
  a poorly calibrated confidence makes the cascade escalate badly.
- ⬜ *(optional, behind a flag)* speculative / co-generation mode (local drafts, cloud verifies).

## Phase 2 — The community hub *(the platform is born here)*

- ⬜ `hub/` (FastAPI + Postgres): `POST /benchmarks`, `GET /benchmarks/leaderboard`,
  `GET /priors?machine=…`, `GET|POST /policies`. **No prompts, ever** — hardware and speed only.
- ⬜ Engine opt-in: submit its micro-benchmark and download priors at startup, so a new machine
  routes well *before* its first local run.
- ⬜ `web/` landing + public leaderboard + docs.
- ⬜ Deploy to `hibrid.tokenstree.eu` (Docker Compose proxied to `127.0.0.1`, nginx vhost,
  certbot) — the engine is **not** hosted here; it's what users download.

## Phase 3 — Launch & community *(continuous)*

- ⬜ Public launch: GitHub, Show HN, r/LocalLLaMA, Product Hunt.
- ⬜ Leaderboard as the viral hook — "your M3 Max does X tok/s, top 12%": personal, shareable,
  competitive, and it feeds back into better routing for everyone.
- ⬜ Contribution programs for **machine benchmarks** (the easiest, most valuable PR) and for
  **routing policies** (privacy-first, low-cost, low-latency, coding presets).
- ⬜ Discussions/Discord, frequent releases, fast issue response.

## The flywheel

Install hibrid → it measures your machine → you get an immediate, personal result worth sharing →
your opt-in benchmark feeds the leaderboard and the priors → the next person with the same
hardware routes well from minute zero. The defensible moat is data nobody else has: routing by
**measured** speed on real user machines, with privacy as a hard override — something a central
cloud gateway structurally cannot replicate.

Deeper detail and the community/hosting strategy live in [`PLAN.md`](PLAN.md).
