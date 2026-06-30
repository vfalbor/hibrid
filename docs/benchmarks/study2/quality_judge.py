#!/usr/bin/env python3
"""LLM-judged answer-quality measurement for hibrid.

For each task we capture TWO answers:
  - AUTO   : what hibrid actually served (routed; may be local_free or paid_cheap)
  - STRONG : forced to the frontier tier (force=cloud_strong)
Then the frontier tier acts as an impartial JUDGE and scores each answer 0.0-1.0
against a one-line criterion, BLIND to which model produced it. We report mean
auto quality vs mean frontier quality and a parity rate, so we can say honestly
whether keeping work off the frontier costs answer quality.
"""
from __future__ import annotations
import json, re, time, random
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8095"
OUT = Path(__file__).resolve().parent
TIMEOUT = httpx.Timeout(180.0)

TASKS = [
    ("loop_refine", "Fix this Python and return only the corrected function: `def add(a, b): retrun a + b`",
     "The function must be syntactically valid Python and return a + b (typo 'retrun' fixed)."),
    ("loop_refine", "Refactor to a single list comprehension: `out=[]\nfor x in xs:\n    if x>0: out.append(x*x)`",
     "Must be equivalent to [x*x for x in xs if x>0]."),
    ("simple", "Classify the sentiment as exactly one of positive/negative/neutral: 'this library saved me hours'",
     "Correct answer is positive."),
    ("simple", "Extract the email address from: 'ping me at sam@example.com tomorrow'. Return only the address.",
     "Correct answer is sam@example.com, with no invented addresses."),
    ("general", "In two sentences, what is the difference between a process and a thread?",
     "Must correctly state processes have separate memory spaces while threads share memory within a process."),
    ("general", "Give one concrete reason to prefer composition over inheritance.",
     "Must give a valid reason (e.g. flexibility, avoids fragile base class / tight coupling)."),
    ("deep_reason", "Prove that any comparison-based sort needs Omega(n log n) comparisons in the worst case. Give the decision-tree argument concisely.",
     "Must use the decision tree: n! leaves, a binary tree of height h has <=2^h leaves, so h>=log2(n!)=Omega(n log n)."),
    ("deep_reason", "Design a backpressure strategy for a multi-producer/single-consumer queue that must never drop messages but also must not OOM. Explain the mechanism and a trade-off.",
     "Must use a bounded queue with blocking/credit-based flow control (producers slow/block when full), and name a trade-off (e.g. latency/throughput or producer stalls)."),
]


def post(client, content, force=None, task_type=None, retries=5):
    body = {"model": "hibrid-auto", "messages": [{"role": "user", "content": content}], "hibrid": {}}
    if task_type:
        body["hibrid"]["task_type"] = task_type
    if force:
        body["hibrid"]["force"] = force
    last = None
    for a in range(retries + 1):
        try:
            r = client.post(f"{BASE}/v1/chat/completions", json=body)
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
            last = r
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
            last = e
        time.sleep(2 * (a + 1) + random.random())
    if hasattr(last, "raise_for_status"):
        last.raise_for_status()
    raise last


def answer_of(resp):
    return (resp.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def chosen_of(resp):
    return resp.get("hibrid", {}).get("chosen", {}) or {}


def judge(client, task, criterion, answer):
    prompt = (
        "You are an impartial grader. Grade the ANSWER to the TASK against the CRITERION.\n"
        "Return ONLY a single number between 0.0 and 1.0 (1.0 = fully correct, 0.0 = wrong/missing). "
        "No words, no explanation.\n\n"
        f"TASK: {task}\nCRITERION: {criterion}\n\nANSWER:\n{answer}\n\nSCORE:"
    )
    resp = post(client, prompt, force="cloud_strong")
    txt = answer_of(resp)
    m = re.search(r"(\d*\.?\d+)", txt)
    if not m:
        return None
    val = float(m.group(1))
    return max(0.0, min(1.0, val))


def main():
    rows = []
    with httpx.Client(timeout=TIMEOUT) as client:
        for i, (tt, content, criterion) in enumerate(TASKS, 1):
            auto = post(client, content, task_type=tt)
            strong = post(client, content, force="cloud_strong", task_type=tt)
            a_ans, s_ans = answer_of(auto), answer_of(strong)
            a_ch, s_ch = chosen_of(auto), chosen_of(strong)
            qa = judge(client, content, criterion, a_ans)
            qs = judge(client, content, criterion, s_ans)
            row = {
                "n": i, "task_type": tt,
                "auto_tier": a_ch.get("tier"), "auto_model": a_ch.get("model"),
                "auto_quality": qa, "frontier_quality": qs,
                "delta": (None if qa is None or qs is None else round(qa - qs, 3)),
            }
            rows.append(row)
            print(f"  {i} {tt:11} auto_tier={str(row['auto_tier']):11} "
                  f"q_auto={qa} q_frontier={qs} delta={row['delta']}")
            time.sleep(1.0)

    valid = [r for r in rows if r["auto_quality"] is not None and r["frontier_quality"] is not None]
    n = len(valid)
    mean_auto = round(sum(r["auto_quality"] for r in valid) / n, 3) if n else None
    mean_front = round(sum(r["frontier_quality"] for r in valid) / n, 3) if n else None
    parity_07 = round(100 * sum(1 for r in valid if r["auto_quality"] >= 0.7) / n, 1) if n else None
    parity_near = round(100 * sum(1 for r in valid if r["auto_quality"] >= r["frontier_quality"] - 0.1) / n, 1) if n else None
    local_rows = [r for r in valid if (r["auto_tier"] or "") == "local_free"]
    mean_auto_local = round(sum(r["auto_quality"] for r in local_rows) / len(local_rows), 3) if local_rows else None

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "engine": BASE,
        "judge": "frontier tier (force=cloud_strong, cli:claude), blind to source model",
        "tasks_judged": n,
        "mean_auto_quality": mean_auto,
        "mean_frontier_quality": mean_front,
        "mean_auto_quality_local_only": mean_auto_local,
        "parity_rate_pct_ge_0_7": parity_07,
        "parity_rate_pct_within_0_1_of_frontier": parity_near,
        "rows": rows,
    }
    (OUT / "quality_judge.json").write_text(json.dumps(summary, indent=2))
    print("\n=== QUALITY SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
