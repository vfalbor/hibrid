---
name: hibrid
description: "Route a task (or a cheap sub-task) through the local hibrid router engine instead of spending frontier tokens. Use when the user types /hibrid, asks to run something 'through hibrid', 'on the local model', 'keep it local/free', or to save frontier tokens on a small task (classify, translate, extract, summarize, trivial code fix, quick draft). Also use as an execution backend for another expertise skill (e.g. /josecela, /viral, /talento, /senior-dev): build the prompt with that skill's framework, then send it through hibrid so a local or cheap tier does the generation. hibrid keeps cheap calls on a local Ollama model (free) and escalates hard ones to the strong tier (the user's Claude subscription via cli:claude, no API key)."
---

# hibrid — route a task through the local router

You are the brain; hibrid is the muscle for cheap work. When this skill is invoked, you send the
task to the local **hibrid** engine instead of answering with your own frontier capacity, then
return the engine's answer and a one-line routing note. hibrid decides per call what runs free on a
local model and what escalates to the strong tier.

## Engine

- Base URL: `http://127.0.0.1:8095` (override with `$HIBRID_BASE`).
- Health: `GET /health`. Live routing stats: `GET /v1/metrics`. Task→model map: `GET /v1/policy`.
- Chat (OpenAI-compatible): `POST /v1/chat/completions`
  ```json
  {"model":"hibrid-auto",
   "messages":[{"role":"system","content":"<optional framing>"},{"role":"user","content":"<task>"}],
   "hibrid":{"task_type":"<type>","force":"<tier?>","allow_cloud":true}}
  ```
- The response carries the answer in `choices[0].message.content`, the routing in
  `hibrid.chosen` (`tier` = `local_free` | `paid_cheap` | `paid_strong`, plus `model`/`backend`),
  whether it escalated in `hibrid.escalated`, and token counts in `usage`.

## task_type — pick the closest

`simple` (translate/classify/extract/summarize) · `loop_refine` (small code fix/refactor) ·
`loop_verify` · `general` (short Q&A) · `interactive` · `batch` · `deep_reason` (genuinely hard
one-shot). The type biases routing: loop/simple stay local-first; deep_reason may escalate.

## How to run it (checklist)

1. **Ensure the engine is up:** `curl -s -m5 http://127.0.0.1:8095/health`. If it does not answer,
   start it: `cd /home/vfalbor/hibrid && nohup .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8095 >/tmp/hibrid_engine.log 2>&1 &` and wait for `/health`.
2. **Classify** the task into a `task_type` (above).
3. **POST** to `/v1/chat/completions` with `model:"hibrid-auto"` and `hibrid.task_type`. Build the
   JSON body safely (e.g. with `python3 -c "import json; ..."`) so quoting/newlines don't break.
4. **Return** the engine's answer to the user, followed by a one-line note:
   `routed via hibrid → <tier>/<model> (<total_tokens> tok)`.
5. **Quality guard (important):** a local 1–3B model is reliable for easy, objective tasks (the
   measured study: ~0.81 vs 0.91 frontier, ~89% retained, but it missed a hard proof). If the task
   is hard, or the local answer looks wrong/low-quality for what the user needs, either re-run with
   `"force":"cloud_strong"` or just answer it yourself. Never ship an obviously bad local answer to
   save tokens — say what you did.
6. **Verify the tier you got.** The router is resilient: if the strong backend (`cli:claude`) is
   momentarily busy/unavailable it silently **falls back to local**, so a `force:"cloud_strong"`
   call can still return `tier:"local_free"`. Always read `hibrid.chosen.tier` from the response;
   if you forced strong but got `local_free`, the strong tier didn't actually run — retry, or
   `POST /v1/node/refresh` to re-probe backends, or answer it yourself. Don't claim "frontier
   quality" for an answer that ran local.

## Flags the user may pass after /hibrid

- a `task_type:` hint — honor it.
- `force local|cloud_cheap|cloud_strong` — set `hibrid.force`.
- `private` / `offline` — set `hibrid.allow_cloud:false` so nothing leaves the machine.
- `--with <skill>` (or another expertise skill is already active) — see composition below.

## Composition with another skill (e.g. /josecela, /viral, /talento, /senior-dev)

You can use another skill's expertise **on top of** hibrid: that skill shapes the prompt, hibrid
executes it.

1. Load/recall the expertise skill's framework (its system guidance, e.g. josecela's copy rules).
2. Put that framework in the **`system`** message and the concrete task in the **`user`** message
   of the hibrid request.
3. Choose the tier honestly:
   - **High-quality generation** (persuasive copy, nuanced analysis, senior code review) needs a
     capable model. A 1–3B local model will not produce josecela-grade copy. So for these, send
     `"force":"cloud_strong"` (the strong tier applies the skill's framework with full quality) —
     or let it route and escalate, but check the result.
   - **Mechanical sub-steps** of that skill (e.g. "extract the 3 keywords", "classify this hook's
     emotion", "draft 5 throwaway subject-line variants") are fine on the local/cheap tier — send
     them with `task_type:"simple"` and no force.
4. Report which skill framed it and which tier ran it:
   `framed by /josecela · routed via hibrid → paid_strong/claude-opus-4-8`.

This is the honest contract: hibrid decides *where* the work runs and saves tokens on the cheap
parts; the expertise skill decides *how good* the prompt is. Keep frontier-grade tasks on a
frontier-grade tier.

## Note on routing this whole Claude Code session

This skill routes *tasks you delegate*, not Claude Code's own agent loop. Pointing Claude Code's own
endpoint at hibrid would need `ANTHROPIC_BASE_URL` + a new session and risks routing the agent's
brain to a 1–3B model (and cli:claude recursion). Don't do that here; delegate at the task level.
