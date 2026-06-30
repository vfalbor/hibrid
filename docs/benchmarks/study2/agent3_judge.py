#!/usr/bin/env python3
"""LLM-judged quality scoring for QualityGuard.

Uses the strong tier (force:cloud_strong) as an impartial, BLIND judge that scores
each answer 0.0-1.0 against a short per-task reference/criteria. Reuses the
local(auto) vs frontier(strong) answer pairs already captured for the 6 SVQ tasks,
and adds 2 genuinely-hard tasks that the router would escalate (here forced LOCAL
vs forced STRONG) so we also measure quality where local is stressed.

To reduce position/source bias the two answers are shown to the judge in RANDOM
order as "Answer 1" / "Answer 2" with NO indication of which model produced which.
180s timeout, retry-on-5xx, ~1s between calls.
"""
from __future__ import annotations
import json, os, random, re, time
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8095"
OUT = Path(__file__).resolve().parent
TIMEOUT = httpx.Timeout(180.0)
random.seed(7)


def chat(client, content, opts, retries=4):
    body = {"model": "hibrid-auto", "messages": [{"role": "user", "content": content}], "hibrid": opts}
    last = None
    for attempt in range(retries + 1):
        r = client.post(f"{BASE}/v1/chat/completions", json=body)
        if r.status_code < 500:
            r.raise_for_status()
            return r.json()
        last = r
        time.sleep(3.0 * (attempt + 1))
    last.raise_for_status()


def answer_of(resp):
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


def tier_of(resp):
    return (resp.get("hibrid", {}).get("chosen", {}) or {}).get("tier")


# Per-task judging criteria/reference (objective where possible).
CRITERIA = {
    "svq_typo": "Task: fix `def add(a, b): retrun a + b`. Correct answer must define add(a,b) that RETURNS a + b (typo 'retrun' fixed to 'return'). 1.0 = correct runnable function; 0 = still broken.",
    "svq_listcomp": "Task: refactor the loop to a SINGLE list comprehension equivalent to [x*x for x in xs if x>0] (squares of positive elements). 1.0 = correct single comprehension; partial if logic slightly off.",
    "svq_reverse": "Task: write reverse(s) so reverse('abc')=='cba'. 1.0 = function that correctly reverses a string (e.g. s[::-1] or reversed). 0 = wrong.",
    "svq_translate": "Task: translate 'The build is green.' to Spanish. 1.0 = a correct, natural Spanish rendering conveying the build/compilation passed/is green; 'verde'/'compilacion'/'build' acceptable. Penalize wrong meaning.",
    "svq_sentiment": "Task: classify sentiment of 'this library saved me hours' as positive/negative/neutral. Reference = positive. 1.0 = says positive; 0 = wrong label. Extra prose is fine if the label is correct.",
    "svq_summary": "Task: summarize in ONE sentence 'The router keeps cheap calls local and only escalates hard ones.' 1.0 = one faithful sentence preserving meaning (cheap stays local, only hard ones escalate). Penalize added/wrong facts or multiple sentences.",
    "hard_reason": "Task: A bat and a ball cost $1.10 total; the bat costs $1.00 MORE than the ball; how much is the ball? Correct final answer = $0.05 (5 cents). 1.0 ONLY if final answer is 0.05 / 5 cents. The intuitive-but-wrong answer 0.10 scores 0.",
    "hard_code": "Task: write is_balanced(s) returning True iff ()[]{}  in s are balanced and correctly nested. 1.0 = a correct stack-based (or equivalent) implementation handling mismatched/nesting; 0.5 if it only counts but ignores nesting/type; 0 if wrong or absent.",
}

# Hard tasks to run fresh: (id, prompt). Local = force local, frontier = force strong.
HARD = [
    ("hard_reason", "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Give the final number."),
    ("hard_code", "Write a Python function `is_balanced(s)` that returns True iff the brackets ()[]{} in s are balanced and correctly nested. Return only the function."),
]


def judge(client, prompt_task, criteria, ans_local, ans_strong):
    """Blind judge: random order, returns (score_local, score_strong, raw)."""
    items = [("local", ans_local), ("strong", ans_strong)]
    random.shuffle(items)
    labels = ["Answer 1", "Answer 2"]
    mapping = {labels[i]: items[i][0] for i in range(2)}
    jp = (
        "You are a strict, impartial grader. Grade two candidate answers to a task "
        "against the criteria. Score each from 0.0 (wrong/missing) to 1.0 (fully correct "
        "and complete). Judge ONLY correctness vs the criteria; ignore length and style; "
        "do not assume which system wrote which answer.\n\n"
        f"TASK: {prompt_task}\n\nCRITERIA: {criteria}\n\n"
        f"{labels[0]}:\n\"\"\"\n{items[0][1].strip()}\n\"\"\"\n\n"
        f"{labels[1]}:\n\"\"\"\n{items[1][1].strip()}\n\"\"\"\n\n"
        "Respond with ONLY a JSON object, no prose:\n"
        '{"answer1": <float 0..1>, "answer2": <float 0..1>}'
    )
    resp = chat(client, jp, {"force": "cloud_strong"})
    raw = answer_of(resp)
    m = re.search(r"\{.*\}", raw, re.S)
    scores = {}
    if m:
        try:
            scores = json.loads(m.group(0))
        except Exception:
            scores = {}
    def grab(key):
        for k in (key, key.replace("answer", "Answer "), key.capitalize()):
            if k in scores:
                return float(scores[k])
        return None
    s1, s2 = grab("answer1"), grab("answer2")
    by_label = {"Answer 1": s1, "Answer 2": s2}
    sl = by_label[[l for l, src in mapping.items() if src == "local"][0]]
    ss = by_label[[l for l, src in mapping.items() if src == "strong"][0]]
    return sl, ss, {"order": [it[0] for it in items], "raw": raw[:400], "parsed": scores,
                    "judge_tier": tier_of(resp)}


def main():
    raw = json.load(open(OUT / "agent3_raw.json"))
    retry = json.load(open(OUT / "agent3_retry.json"))

    # Build local/strong answer pairs for the 6 SVQ tasks (reuse captured answers).
    pairs = []  # (id, prompt_task, local_answer, local_tier, strong_answer)
    svq_prompt = {r["id"]: r["prompt"] for r in raw["svq"]}
    for r in raw["svq"]:
        sid = r["id"]
        local_ans = r["auto"]["answer"] or ""
        local_tier = r["auto"]["tier"]
        if sid == "svq_listcomp" and not local_ans:  # auto 502'd first pass; use re-run
            local_ans = retry["svq_listcomp_auto"]["answer"] or ""
            local_tier = retry["svq_listcomp_auto"]["tier"]
        pairs.append((sid, svq_prompt[sid], local_ans, local_tier, r["strong"]["answer"] or ""))

    with httpx.Client(timeout=TIMEOUT) as client:
        # Fresh hard tasks: forced local vs forced strong.
        for hid, prompt in HARD:
            t0 = time.time()
            rl = chat(client, prompt, {"task_type": "deep_reason", "force": "local"})
            la = answer_of(rl); lt = tier_of(rl)
            time.sleep(1.0)
            rs = chat(client, prompt, {"task_type": "deep_reason", "force": "cloud_strong"})
            sa = answer_of(rs)
            pairs.append((hid, prompt, la, lt, sa))
            print(f"  fetched {hid} local_tier={lt} ({round(time.time()-t0,1)}s)")
            time.sleep(1.0)

        # Judge each pair.
        rows = []
        for sid, ptask, la, lt, sa in pairs:
            if not la or not sa:
                rows.append({"task": sid, "local_tier": lt, "local_quality": None,
                             "frontier_quality": None, "delta": None, "note": "missing answer"})
                print(f"  {sid:14s} SKIP (missing answer)")
                continue
            sl, ss, meta = judge(client, ptask, CRITERIA[sid], la, sa)
            delta = (round(sl - ss, 3) if (sl is not None and ss is not None) else None)
            rows.append({"task": sid, "local_tier": lt, "local_quality": sl,
                         "frontier_quality": ss, "delta": delta,
                         "judge_order": meta["order"], "judge_raw": meta["raw"]})
            print(f"  {sid:14s} local={sl} frontier={ss} delta={delta} (order={meta['order']})")
            time.sleep(1.0)

    # Aggregate.
    scored = [r for r in rows if r["local_quality"] is not None]
    locally_routed = [r for r in scored if (r["local_tier"] or "") == "local_free"]
    mean_local = round(sum(r["local_quality"] for r in scored) / len(scored), 3) if scored else None
    mean_front = round(sum(r["frontier_quality"] for r in scored) / len(scored), 3) if scored else None
    # parity over LOCALLY-ROUTED tasks: score >= 0.7 OR within 0.1 of frontier
    base = locally_routed or scored
    parity = [r for r in base if r["local_quality"] >= 0.7 or (r["frontier_quality"] - r["local_quality"]) <= 0.1]
    out = {
        "method": "Strong tier (force:cloud_strong) as a blind judge; answers shown in random "
                  "order as Answer 1/2 with no source label; scored 0..1 vs per-task criteria. "
                  "6 SVQ answer-pairs reused from agent3_raw.json; 2 hard tasks (hard_reason, "
                  "hard_code) fetched fresh as force:local vs force:cloud_strong so local is "
                  "stressed on work it would normally escalate.",
        "criteria": CRITERIA,
        "rows": rows,
        "aggregate": {
            "tasks_scored": len(scored),
            "mean_local_quality": mean_local,
            "mean_frontier_quality": mean_front,
            "mean_delta_local_minus_frontier": (round(mean_local - mean_front, 3)
                                                 if mean_local is not None else None),
            "locally_routed_tasks": len(locally_routed),
            "parity_basis": "locally_routed" if locally_routed else "all_scored",
            "parity_threshold": "local>=0.7 OR within 0.1 of frontier",
            "parity_count": len(parity),
            "parity_rate_pct": round(100 * len(parity) / len(base), 1) if base else None,
        },
        "limitations": "Single judge (one strong model), small n (8 tasks), short objective "
                       "tasks. Judge could be lenient on its own style of answer despite blinding; "
                       "scores are point estimates, not averaged over multiple judges or seeds.",
    }
    (OUT / "agent3_quality.json").write_text(json.dumps(out, indent=2))
    print("\n=== AGGREGATE ===")
    print(json.dumps(out["aggregate"], indent=2))
    return out


if __name__ == "__main__":
    main()
