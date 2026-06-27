# hibrid — work plan, implementation & community strategy

> How to go from the current scaffold to a **community platform**: open-source, hosted on the
> tokenstree.eu server under `hibrid.tokenstree.eu`, integrated coherently with GitHub, with a
> community growth engine. (Spanish original: [PLAN.es.md](PLAN.es.md).)

---

## 0. The idea in one sentence

hibrid is an **open-source local tool** ("the router that knows your machine") + a **community
service** that aggregates, anonymously and opt-in, the real speeds (tok/s) each machine gets with
each model. That collaborative database improves routing for **everyone** → a network effect.
That is the heart of the community.

**Why it works as a community:** the value each user contributes (their real benchmark) benefits
the others, and in return they get better recommendations for their hardware. It's the same
pattern as the "Home GPU LLM Leaderboards", but actionable from inside the router.

---

## 1. The two halves of the system

hibrid is NOT a central gateway (local inference runs on each user's machine). So it splits into
two components with distinct responsibilities:

### A) `hibrid-engine` (runs on the user's machine) — ALREADY built
The current scaffold: local FastAPI, OpenAI- and Anthropic-compatible API, profiler, micro-
benchmark, utility router, cascade with calibration, and the **adaptive orchestration layer**
(reach the paid tier through an agent CLI / skills service / harness passthrough — no API key).
This is the **open-source product** people download and run. No account required. Private by
default.

### B) `hibrid-hub` (hosted on `hibrid.tokenstree.eu`) — to build
The **community service**. It processes nobody's prompts. Only:
1. **Benchmark Registry / Leaderboard** — receives opt-in submissions `(machine, model, quant,
   tok/s)` and aggregates them; serves speed "priors" so a new user routes well *before* their
   first micro-benchmark.
2. **Policy Registry** — shares routing presets (λ profiles: "privacy-first", "low-cost",
   "low-latency", "coding") published and downloaded by the community.
3. **Landing + Docs** — the public face, one-line install, the narrative.
4. **Optional dashboard** — for anyone who wants aggregated telemetry of their own usage.

```
   User's machine                          hibrid.tokenstree.eu (community)
   ┌──────────────────┐   opt-in submit     ┌─────────────────────────────┐
   │  hibrid-engine    │ ── (machine,model,  │  hibrid-hub                  │
   │  (OSS, local)     │     tok/s) ───────► │  • Benchmark Registry/Board  │
   │  prompts NEVER    │ ◄── priors/policies │  • Policy Registry            │
   │  leave here       │                     │  • Landing + Docs + Dashboard│
   └──────────────────┘                     └─────────────────────────────┘
```

Privacy as a founding principle: **the user's prompts and data never reach the hub**; only
anonymous hardware/speed metrics, and only *if the user turns it on*.

---

## 2. Main parts of the system (component map)

| Component | Where it runs | Status | Tech |
|---|---|---|---|
| Router + utility + cascade | engine (local) | ✅ done | FastAPI/Python |
| **Execution profiles by task type** (loops local-first) | engine (local) | ✅ done | see `EXECUTION_PROFILES.md` |
| **Task → LLM policy matrix** | engine (local) | ✅ done | `task_policy.py`, see `ORCHESTRATION.md` |
| **Adaptive orchestration backends (no API key)** | engine (local) | ✅ done | `backends.py` (CLI/service/passthrough) |
| Hardware profiler + micro-benchmark | engine (local) | ✅ done | psutil/pynvml/system_profiler |
| Local provider (OpenAI-compat) | engine (local) | ✅ done | httpx |
| Confidence calibration (online Platt) | engine (local) | ✅ done | Python |
| kNN router over history | engine (local) | ⬜ next | embeddings + SQLite |
| RouterBench/RouterEval eval | engine (CI) | ⬜ next | public dataset |
| **Benchmark Registry + Leaderboard** | hub (.eu) | ⬜ to build | FastAPI + Postgres |
| **Policy Registry** | hub (.eu) | ⬜ to build | FastAPI + Postgres |
| **Landing + Docs + Dashboard web** | hub (.eu) | ⬜ to build | React/Vite or Astro |
| Deployment (Docker + nginx + certbot) | .eu server | ⬜ to build | docker-compose |

---

## 3. Hosting on the tokenstree.eu server

Server: the machine serving `tokenstree.eu` (IP in the private infra inventory, not in this
repo). Detected convention: nginx on host with `sites-available/`, **certbot** for certs, apps in
**Docker Compose** proxied to `127.0.0.1:<port>`. We replicate that mould.

**Proposed subdomain: `hibrid.tokenstree.eu`** (consistent with the rest of the ecosystem).

Deploy steps (same pattern as the other apps):
1. **DNS**: A record `hibrid.tokenstree.eu` → server IP.
2. **Repo on the server**: `git clone` into `/opt/hibrid`.
3. **Docker Compose** for the hub: `hibrid-hub` (FastAPI) on `127.0.0.1:8096` + `postgres`
   (registry). The local **engine is NOT hosted here** — it's what the user downloads.
4. **nginx vhost** `/etc/nginx/sites-available/hibrid` → `proxy_pass http://127.0.0.1:8096;` +
   the ACME challenge location. `ln -s` into `sites-enabled/`.
5. **Certbot**: `certbot --nginx -d hibrid.tokenstree.eu` (auto-renew).
6. **CI/CD** (§4): a workflow that on each release does `ssh` + `docker compose pull && up -d`.

> The engine and the hub are **different repos/images**. Only the **hub** lives on `.eu`. The
> engine is distributed via PyPI / Docker Hub / `pip install hibrid` to run locally.

---

## 4. Coherent GitHub integration

Mirror the structure already used across the ecosystem (Dockerfile + docker-compose +
CONTRIBUTING + LICENSE + README), raised to a community-project standard.

**Recommended repo structure: a `hibrid` monorepo** with clear folders, so engine and hub evolve
together and share schemas:

```
hibrid/                      (github.com/vfalbor/hibrid)
├── engine/                  # the local OSS (what's built)
├── hub/                     # community backend (FastAPI + Postgres)
├── web/                     # landing + docs + dashboard
├── docs/                    # research, architecture, this plan
├── .github/                 # CI, deploy, issue/PR templates
├── CONTRIBUTING.md · CODE_OF_CONDUCT.md · LICENSE (Apache-2.0) · SECURITY.md
└── README.md                # ✅ written
```

**GitHub hygiene that builds trust and community:**
- **Permissive licence** (Apache-2.0): key to adoption and contributions.
- **Visible green CI**: a tests badge (the engine suite already runs).
- **Semantic releases** + changelog; the engine published to **PyPI** (`pip install hibrid`) and
  **Docker Hub** for one-line startup.
- **GitHub Discussions** enabled (a frictionless community channel).
- **Issues labelled `good first issue`** — above all: "add your machine's benchmark".
- **Benchmark contribution template**: a structured PR/issue that adds `(machine, model, quant,
  tok/s)` to the registry → turns users into contributors.
- A **`tokenstree` GitHub org** grouping hibrid with the rest → coherent brand presence and
  cross-discovery.

---

## 5. Phased work plan

### Phase 0 — Consolidate the engine (≈1 week) · *almost done*
- [x] Scaffold engine + tests + research/architecture docs.
- [x] AI-agnostic (Anthropic + OpenAI dialects) and the **no-API-key orchestration layer**.
- [ ] Packaging: `pyproject.toml`, publish to PyPI and Docker Hub.
- [ ] `pip install hibrid && hibrid serve` working in one line.
- [x] CI on GitHub Actions (tests).

### Phase 1 — Router quality (2–3 weeks)
- [ ] **kNN router** over the machine's own history (improves with use).
- [ ] Evaluation against **RouterBench/RouterEval** → a publishable KPI ("% resolved locally at
      parity"). This is the number that earns technical credibility.
- [ ] Harden the **confidence calibration** (the #1 risk the team flagged).
- [ ] (optional) **co-generation** mode (speculative decoding) behind a flag.

### Phase 2 — The community hub (3–4 weeks) · *the platform is born here*
- [ ] `hub/` FastAPI + Postgres: `POST /benchmarks`, `GET /benchmarks/leaderboard`,
      `GET /priors?machine=…`, `GET|POST /policies`.
- [ ] The engine: opt-in to **submit** its micro-benchmark and **download** priors at startup.
- [ ] `web/` landing + public leaderboard + docs.
- [ ] Deploy to `hibrid.tokenstree.eu` (Docker + nginx + certbot, §3).

### Phase 3 — Launch & community (continuous)
- [ ] Launch on GitHub (public), Show HN, r/LocalLLaMA, Product Hunt.
- [ ] The leaderboard as the viral hook ("see how your Mac/RTX does vs the average").
- [ ] Programs for benchmark and routing-policy contributions.
- [ ] Discord/Discussions; frequent releases; fast issue response.

---

## 6. How the community is built (the flywheel)

1. **Entry hook**: "install hibrid and find out which LLM really runs on YOUR machine" → the
   micro-benchmark gives a personal, immediate result people want to share.
2. **A contribution that benefits everyone**: that benchmark feeds the leaderboard and the priors
   → the next user with the same hardware routes well from minute zero.
3. **Status and comparison**: the public leaderboard ("your M3 Max does X tok/s, top 12%") is
   shareable, competitive content — the virality engine of GPU leaderboards.
4. **Deeper contribution**: routing policies, new local backends, calibrators → technical
   contributors (via `good first issue` and a clear CONTRIBUTING).
5. **tokenstree brand coherence**: linked from tokenstree.eu and the rest of the ecosystem; same
   "user tools, privacy first" aesthetic and narrative.

**Defensible differentiator** (confirmed by the research team): nobody else routes by **measured**
speed on the user's machine, offers privacy as a hard override, **and** reaches strong models
through the user's existing agent subscription with no API key. The community of real benchmarks
is also a **data moat** a cloud gateway cannot replicate.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Poor confidence calibration → bad escalation | Dedicated tests + eval (Phase 1); it's the top technical priority |
| Ollama adds auto-routing and invades us | Multi-backend + privacy/utility knobs + data community; move fast |
| Reinventing plumbing (gateways have it) | Build transport on LiteLLM if useful; focus on the *decision layer* |
| Privacy: benchmarks leak data | Only anonymous hardware/speed metrics, opt-in; never prompts |
| Community doesn't take off | Leaderboard hook + one-line install + `good first issue` benchmarks |
