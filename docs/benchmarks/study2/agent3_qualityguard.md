# Study 2 - Agent 3 (QualityGuard): routing correctness & savings-vs-quality

**Engine:** `http://127.0.0.1:8095` - node `cpu_8gb` (2 cores, 8 GB, no GPU),
local models `llama3.2:3b` + `qwen2.5-coder:1.5b`, strong tier via `cli:claude`
(`claude-opus-4-8`, no per-token price). Date: 2026-06-29.

**Method:** real calls to `POST /v1/chat/completions`; tier read from
`response.hibrid.chosen`, tokens from `response.usage`. 180 s timeout,
retry-on-5xx, ~1 s between calls (imitating `token_savings_run.py`). The engine
was under concurrent 3-agent load on 2 cores; 4 slow local calls returned
transient `502 Bad Gateway` and were re-run successfully. All numbers below are
real measured results (`agent3_raw.json` + `agent3_retry.json`).

---

## 1. Correctness matrix - 11/12 PASS

| Rule | Intent | Expected | Observed | Verdict |
|---|---|---|---|---|
| simple_local | simple stays local | `local_free` | **`paid_cheap`** | **FAIL** |
| loop_refine_local | loop_refine stays local | `local_free` | `local_free` | PASS |
| batch_local | batch stays local | `local_free` | `local_free` | PASS |
| loop_refine_complex_local | loop never -> strong | not `paid_strong` | `local_free` | PASS |
| deep_reason_escalates | hard one-shot may escalate | paid tier | `paid_cheap` | PASS |
| pii_email_local | email -> local despite deep_reason | `local_free` | `local_free` | PASS |
| pii_phone_ssn_local | SSN -> local despite deep_reason | `local_free` | `local_free` | PASS |
| pii_card_local | card -> local despite deep_reason | `local_free` | `local_free` | PASS |
| allow_cloud_false_local | offline mode -> local | `local_free` | `local_free` | PASS |
| force_strong | force honored | `paid_strong` | `paid_strong` | PASS |
| force_local | force honored | `local` | `local_free` | PASS |
| force_cloud_cheap | force honored | `paid_cheap` | `paid_cheap` | PASS |

**Verdict:** every **hard override is correct** - PII (email / SSN / credit-card)
forces local even when `task_type=deep_reason`; `allow_cloud=false` stays local;
`force` to local/cheap/strong is always honored; `loop_refine` never jumps to the
strong tier even when phrased as complex; `deep_reason` is allowed to escalate off
local.

The single failure is a **soft** rule, not a hard one: `simple` tasks do **not**
stay local. `simple`'s policy ladder is `local_free -> paid_cheap` and the utility
argmax consistently prefers the cheap paid tier (reproduced on all 3 `simple`
tasks in section 2). So in this deployment "simple stays local" is false - simple
goes to `paid_cheap` (haiku). It still never reaches the expensive frontier tier.

---

## 2. Savings vs quality

Question: does keeping work off the frontier cost answer quality? Six tasks run
under **auto** routing and again **forced to `cloud_strong`**; answers compared on
objective checks. Frontier = `paid_strong`.

| Task | type | Auto tier | Auto OK? | Strong OK? | Quality equal? | Frontier tok WITH / WITHOUT |
|---|---|---|---|---|---|---|
| svq_typo | loop_refine | local_free | yes | yes | yes | 0 / 36 |
| svq_listcomp | loop_refine | local_free | yes | yes | yes | 0 / 38 |
| svq_reverse | loop_refine | local_free | yes | yes | yes | 0 / 118 |
| svq_translate | simple | paid_cheap | yes | yes | yes | 0 / 118 |
| svq_sentiment | simple | paid_cheap | yes | yes | yes | 0 / 30 |
| svq_summary | simple | paid_cheap | yes | yes | yes | 0 / 44 |

**Totals:** 6 tasks - auto kept **3 fully local** (loop_refine) and routed **3 to
the cheap paid tier** (simple); **0 went to the frontier**. Frontier tokens WITH
hibrid = **0**, WITHOUT (all forced strong) = **384**. **Frontier tokens avoided =
384 (100%)** for this set, **with zero quality regressions**.

**Finding:** on every task it kept off the frontier, the router lost **no** answer
quality - identical corrected code (`return a + b`, `s[::-1]`, `[x**2 for x in xs
if x>0]`), the exact label `positive`, and faithful one-sentence
summary/translation - matching the opus answers on the objective checks. The
strong answers were sometimes longer (explanatory prose), but not more *correct*.

So local/cheap routing **did save the frontier tokens without dropping quality**
on the tasks it kept off the frontier.

---

## 3. Honest caveats

- **Only loop_refine stayed fully local.** The 3 "simple" tasks went to the cheap
  paid tier, not local. The 100%-frontier-avoided headline is real, but only
  half of it is "fully local"; the other half is "cheap tier instead of frontier".
- **Easy, objective tasks only.** These probes are short and have crisp right
  answers, which is where a 1-3B local model is strongest. This does **not** show
  local quality holds on genuinely hard reasoning - and the router agrees: it
  escalates `deep_reason` off local rather than trusting the small model.
- **No output-quality feedback in the router.** hibrid escalates on *pre-execution*
  features (complexity heuristic, task_type, PII), not on whether the local answer
  was actually good. It cannot catch a case where the local model is confidently
  wrong on a task it decided to keep local.
- **Load / 502s.** Under 3-agent load on 2 cores, slow local calls (80-120 s)
  returned transient 502s; 4 calls were re-run. Engine `avg_latency_s` rose from
  ~6.5 s to ~16 s during the run. This is an infra/capacity effect, not a routing
  defect.
- **No dollar figure.** The strong tier is a CLI Claude subscription with no
  per-token price, so savings are frontier **tokens** avoided, not dollars.

---

## 4. How the field frames "saving money without losing quality"

- **FrugalGPT** (Chen et al., 2023): LLM **cascade** - cheap model first, escalate
  only when a learned scorer rejects the cheap answer; matches GPT-4 quality at up
  to ~98% lower cost. The canonical result. <https://arxiv.org/abs/2305.05176>
- **Hybrid LLM** (Ding et al., ICLR 2024): a difficulty-predicting router with a
  **tunable quality target** routes easy queries to a small model - up to ~40%
  fewer large-model calls at **no** measured quality drop.
  <https://arxiv.org/abs/2404.14618>
- **RouterBench** (Hu et al., 2024, UC Berkeley): 405k-outcome benchmark that
  scores routers on the **cost-quality plane** (convex hull / AIQ). Lesson: report
  *quality at a cost*, never cost alone. <https://arxiv.org/abs/2403.12031>
- **Confidence-based cascades:** use the small model's **output uncertainty** as
  the escalation signal; surveys report cutting cost ~45-85% while retaining ~95%
  of quality. hibrid escalates on cheap pre-execution features instead - cheaper,
  but blind to whether the kept-local answer was actually good.
  <https://arxiv.org/html/2404.14618>
- **Practitioner consensus** (RouterBench / Martian): route first to skip
  mismatched tiers, then cascade within a tier; treat privacy/compliance (keep PII
  local) as **hard overrides outside** the cost-quality optimization - exactly the
  layering hibrid implements with PII->local and `allow_cloud=false`.
  <https://withmartian.com/post/introducing-routerbench>
