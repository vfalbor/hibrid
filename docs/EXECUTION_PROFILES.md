# hibrid — execution profiles (routing by task type)

Routing isn't driven only by the complexity of a single query. It's driven by the **task type
and its execution pattern** — because some patterns flip the economics. The clearest case is
**loops**.

A code-refinement loop or an iterative QA run makes dozens or hundreds of calls. Each is cheap,
but the total is large. Sent to paid tokens, the cost explodes. So a loop should run
**local-first** and escalate sparingly.

So the task type is a first-class routing signal, above one-shot complexity. hibrid models this
with **execution profiles**.

## Tiers (free/local ↔ paid mapping)

| Tier | What | Cost | Privacy |
|---|---|---|---|
| `local_free` | open-weights on the user's machine (Ollama/llama.cpp/vLLM) | ~0 | maximal |
| `paid_cheap` | low-cost paid models (Haiku, gpt-4o-mini) | low | external |
| `paid_strong` | top paid models (Opus, gpt-4o) | high | external |

The registry resolves each tier to a concrete model available on this machine/account. Profiles
speak in tiers, so the same profile works on any hardware.

## Built-in profiles

| Profile | Tier order | Escalates up to | For |
|---|---|---|---|
| **loop_refine** | local_free → paid_cheap | paid_cheap (never strong per-iteration) | refactor loops, iterative QA, test-fix-retest |
| **loop_verify** | paid_strong → paid_cheap → local_free | paid_strong | the single final check of a loop |
| **deep_reason** | paid_strong → local_free → paid_cheap | paid_strong | one-shot hard task (architecture, proof, hard debug) |
| **simple** | local_free → paid_cheap | paid_cheap | classify, extract, translate, short summary |
| **interactive** | local_free → paid_cheap → paid_strong | paid_cheap | live chat (latency weighted higher) |
| **batch** | local_free → paid_cheap | paid_cheap | bulk, no urgency (maximize local) |
| **general** | local_free → paid_cheap → paid_strong | paid_strong | balanced (pure utility) |

Each profile adds: allowed tier order, a per-tier utility bonus (subsidize local in loops),
optional λ overrides, and the cascade's escalation cap. `loop_refine` gives a strong local bonus
and excludes `paid_strong`: even if an iteration looks hard, the loop never jumps to the expensive
model.

## Who picks the profile

1. **Declared by the tool/skill** (preferred): `{"hibrid": {"task_type": "loop_refine"}}`. The
   loop knows it's a loop.
2. **Inferred by hibrid** from query signals (loop/verify/simple/deep-reason hints) if not declared.
3. **Forced by the user** via knobs (`force`, `allow_cloud`, λ) — highest priority.

Every response carries the chosen profile, tier and model, and whether/why it escalated. The user
never has to choose, but can always see the decision.

## Example: a loop

```
loop_refine declared:
  iter 1..N: hibrid → local_free                      [cost 0]
             if calibrated confidence drops → paid_cheap (cap)
             never paid_strong inside the loop
  on finish: one call task_type=loop_verify → paid_strong  [once]
```

Most of the loop runs free locally; the paid model is reserved for the one final sign-off.

Status: implemented and tested (`tests/test_router.py`). Profiles are designed to be shareable —
the community can publish task-type → tier policies.
