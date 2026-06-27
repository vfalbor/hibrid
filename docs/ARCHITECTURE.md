# hibrid — architecture

```
   any AI tool (Claude Code, Codex, aider, opencode, your own client)
        │  speaks OpenAI or Anthropic dialect → points its base URL at hibrid
        ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │                          hibrid (FastAPI)                          │
 │  /v1/chat/completions  (OpenAI)     /v1/messages  (Anthropic)      │
 │            └──────────────┬──────────────┘                         │
 │                  dialects.py  (translate in/out)                   │
 │                           ▼                                        │
 │  1) classifier  → features: complexity, PII, language, code, task  │
 │  2) router      → argmax U(d), task_policy + profile + overrides   │
 │       uses: registry (local models + measured tok/s · discovered   │
 │             backends) · models_catalog (capability per task,       │
 │             local + orchestrated) · task_policy (task→LLM matrix)   │
 │  3) execute on chosen destination                                  │
 │  4) cascade: if local & confidence low → escalate (profile cap)    │
 │  5) log route → SQLite (history for kNN + KPIs)                    │
 └───────────┬──────────────────┬──────────────────┬────────────────┘
             ▼                  ▼                  ▼
       local_free          paid_cheap          paid_strong
   Ollama/llama.cpp/vLLM   best cheap model    best strong model
   (OpenAI-compatible)    ──── reached via an orchestration backend ────
                          cli:claude/codex/opencode/copilot · skills
                          service · harness passthrough   (NO API key)
```

## Modules

| Module | Responsibility |
|---|---|
| `dialects.py` | Translate OpenAI ↔ Anthropic ↔ internal so hibrid is AI-agnostic |
| `profiler.py` | Detect RAM/VRAM/CPU/chip → machine class + max Q4 model |
| `registry.py` | Discover local models + orchestration backends; startup micro-benchmark of real tok/s (cached) |
| `backends.py` | Orchestration adapters (CLI / skills-service / passthrough) + discovery + adaptive pick — the no-API-key strong tier |
| `task_policy.py` | The explicit task_type → (axis, tier ladder, model preference) matrix |
| `models_catalog.py` | Curated capability-per-task tables (local **and** orchestrated); pick best model for the task that fits |
| `classifier.py` | Cheap query features (length, language, code, PII, complexity, task type) |
| `router.py` | Utility function `U(d)` + task policy + execution-profile tiers + hard overrides → argmax |
| `confidence.py` | Raw confidence → online Platt calibration (escalation gate) |
| `main.py` | Endpoints + shared `_route_and_run` core + cascade |
| `db.py` | SQLite route history (kNN priors + KPIs) |

## Key decisions

- **One core, many dialects.** `_route_and_run` is shared; only the request/response grammar
  differs per endpoint. Adding a dialect is a translation function, not a new pipeline.
- **Transparency = compatible API.** Same format as Ollama/vLLM/OpenAI/Anthropic; no custom
  protocol. Tools adopt hibrid by changing a base URL.
- **No API keys.** The paid tier is reached through an already-authenticated orchestration
  backend (an agent CLI on your subscription, a skills service, or harness passthrough), chosen
  adaptively from whatever is available. See [ORCHESTRATION.md](ORCHESTRATION.md).
- **Privacy is a hard override**, not a soft weight: detected PII pins execution to local.
- **The escalation threshold is derived** from utility + calibrated confidence; the calibrator
  improves with use.
- **Measured, not guessed.** A startup micro-benchmark replaces spec-sheet estimates with the
  machine's real tokens/sec.

## Known gaps

- Streaming (SSE) for both dialects is not yet implemented — required for fully transparent use
  under some tools. Tracked in [ROADMAP.md](ROADMAP.md).
