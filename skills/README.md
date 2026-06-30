# skills

Claude Code / agent skills shipped with hibrid.

## `hibrid` — route a task through the local router

`skills/hibrid/SKILL.md` is an agent skill that delegates a task (or a cheap sub-task) to the local
hibrid engine instead of spending frontier tokens. The agent stays the brain; hibrid is the muscle
for cheap work, keeping easy calls on a local Ollama model (free) and escalating hard ones to the
strong tier (the user's Claude subscription via `cli:claude`, no API key).

### Install (Claude Code)

Skills live in `~/.claude/skills/<name>/SKILL.md`. Symlink this one so the repo stays the single
source of truth:

```bash
ln -sfn "$(pwd)/skills/hibrid" ~/.claude/skills/hibrid
```

Then `/hibrid <task>` is available in a new session. The engine must be running
(`./run.sh`, on `:8095`).

### What it does

- Classifies the task, POSTs to `http://127.0.0.1:8095/v1/chat/completions` with `model:hibrid-auto`,
  returns the answer plus a one-line routing note (`tier/model`, tokens).
- Honors flags: a `task_type:` hint, `force local|cloud_cheap|cloud_strong`, `private`/`offline`
  (`allow_cloud:false`).
- **Quality guard:** a 1–3B local model is reliable only for easy/objective tasks; the skill checks
  the returned tier and escalates (or hands back to the agent) when local quality isn't enough.

### Composition with other skills

`/hibrid` can be the execution backend for an expertise skill (e.g. `/josecela`, `/viral`,
`/talento`, `/senior-dev`): that skill's framework goes in the `system` message, the task in `user`,
and hibrid routes it. Mechanical sub-steps run local/cheap; frontier-grade generation is sent to the
strong tier so the expertise isn't lost on a small model. See the skill body for the honest contract.
