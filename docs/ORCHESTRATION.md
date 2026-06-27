# hibrid — orchestration & the task → LLM policy

This is the answer to two questions: **"which LLM does hibrid use for which task?"** and
**"how does it reach a strong model without an API key?"**

## No API keys — orchestrated backends

hibrid sits *under* your AI tools, so it reaches stronger capability the same way you already
pay for it: through an **already-authenticated orchestration layer**, never a separate
pay-per-token key. Three mechanisms sit behind one interface, and hibrid **adaptively** uses
whichever is available and best at the moment:

| Backend | Mechanism | How it runs the call | Auth |
|---|---|---|---|
| `cli:claude` / `cli:codex` / `cli:opencode` / `cli:copilot` | **CLI** | shells out to the headless agent (`claude -p`, `codex exec`, `opencode run`, `copilot -p`) | your existing subscription / seat |
| `service` | **service** | calls a local "skills" service that orchestrates agents underneath | the service owns auth |
| `passthrough` | **passthrough** | forwards upstream reusing the harness's own session token (e.g. Claude Code OAuth) | the harness's session, not a key |

At startup hibrid **discovers** which of these are present: which agent CLIs are installed and
logged in, whether a skills service answers, whether a passthrough token exists. Each backend
advertises the models it can serve and a measured latency. The router then picks, per request,
the lowest-latency available backend that serves the chosen model. If the preferred backend is
down or logged out, the next one falls in automatically — that is the adaptive part.

`GET /v1/node` shows the discovered backends; `GET /v1/policy` shows the matrix below.

## The task → LLM policy (explicit matrix)

Routing is driven by **task type → tier ladder → best model for the task axis**. The matrix
lives in `backend/task_policy.py` (one auditable source of truth):

| task_type | axis | tier ladder (cheap → strong) | paid cap | for |
|---|---|---|---|---|
| `loop_refine` | code | local_free → paid_cheap | **paid_cheap** | refactor/QA loops — never the strong model per iteration |
| `loop_verify` | code | paid_strong → paid_cheap → local_free | — | the single final check of a loop |
| `deep_reason` | reasoning | paid_strong → local_free → paid_cheap | — | one-shot hard task (architecture, proof, hard debug) |
| `simple` | general | local_free → paid_cheap | paid_cheap | classify, extract, translate, short summary |
| `interactive` | general | local_free → paid_cheap → paid_strong | — | live chat (latency weighted higher) |
| `batch` | general | local_free → paid_cheap | paid_cheap | bulk, no urgency (maximize local) |
| `general` | general | local_free → paid_cheap → paid_strong | — | balanced (pure utility) |

The **axis** (`general` / `code` / `reasoning`) decides *which competence is measured* — for
both local and orchestrated models. The **tier ladder** is the cost preference; the per-request
λ weights and the escalation cap come from `profiles.py` and stay consistent with this table.

## Which concrete model per tier

Within a tier, hibrid does **not** hardcode one model. It picks the best *available* model for
the task axis:

- **local_free** — best local model for the axis that fits the machine
  (`models_catalog.best_local_for`). See [MODELS.md](MODELS.md).
- **paid_cheap / paid_strong** — best orchestrated model for the axis in that tier
  (`models_catalog.best_orchestrated_for`), among those an available backend can serve.

Curated per-axis capability of orchestrated models (priors, refined by use):

| Model | tier | general | code | reasoning | quota cost |
|---|---|---|---|---|---|
| claude-opus-4-8 | paid_strong | 0.97 | 0.95 | **0.98** | 1.00 |
| gpt-4o | paid_strong | 0.95 | 0.92 | 0.94 | 0.80 |
| claude-sonnet-4-6 | paid_strong | 0.93 | 0.92 | 0.93 | 0.55 |
| claude-haiku-4-5 | paid_cheap | 0.85 | 0.80 | 0.80 | 0.18 |
| gpt-4o-mini | paid_cheap | 0.80 | 0.76 | 0.76 | 0.10 |

Selection is by axis capability; near-ties break toward lower quota cost. The cross-tier cost
trade-off (is the strong tier worth it?) is resolved by the router's utility function, not here.

## Worked example: a refactor loop on a coding agent

```
Claude Code → ANTHROPIC_BASE_URL=hibrid → task_type=loop_refine (axis=code)
  iter 1..N: local_free → best local code model (e.g. qwen2.5-coder)      [no quota]
             if calibrated confidence drops → paid_cheap (cap), via the
             lowest-latency available backend (cli:claude → haiku)
             never paid_strong inside the loop
  on finish: one call task_type=loop_verify → paid_strong (opus) via cli:claude  [once]
```

Most of the loop runs free and local; a strong model is spent only on the final sign-off, and it
is reached through your **subscription** via an agent backend — no API key anywhere.
