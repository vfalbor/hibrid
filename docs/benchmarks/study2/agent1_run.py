#!/usr/bin/env python3
"""Study 2 / Agent "TokenBench": measured before/after of frontier-tier token
consumption with vs without the hibrid router.

For EVERY task we call the engine twice:
  - WITH  hibrid: auto routing, {"hibrid":{"task_type":...}}
  - WITHOUT      : force the strong tier, {"hibrid":{...,"force":"cloud_strong"}}
This yields a real measured before/after (not only a counterfactual sum).

Strong tier = the user's Claude subscription via cli:claude (no per-token $),
so savings are expressed as frontier-tier TOKENS and CALLS avoided.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8095"
OUT = Path(__file__).resolve().parent
TIMEOUT = httpx.Timeout(180.0)
LOCAL_TIER = "local_free"

# 3 distinct workloads, each (task_type, prompt). Prompts kept short.
WORKLOADS = {
    # (a) long code-refine loop — the agent-loop case, 12 small edits
    "A_refine_loop": [
        ("loop_refine", "Fix: `def mul(a,b): retrun a*b`. Return only the function."),
        ("loop_refine", "Refactor to comprehension: `r=[]\nfor x in xs:\n if x%2==0: r.append(x)`"),
        ("loop_refine", "Add a docstring: `def kebab(s): return s.lower().replace(' ','-')`"),
        ("loop_refine", "Write `is_palindrome(s)` so `is_palindrome('aba')` is True."),
        ("loop_refine", "Rename `d` to a readable name: `d={}; d['k']=1`"),
        ("loop_refine", "Add type hints: `def total(xs): return sum(xs)`"),
        ("loop_refine", "Guard empty list: `def first(xs): return xs[0]`"),
        ("loop_refine", "Use f-string: `print('id=' + str(i))`"),
        ("loop_refine", "Convert to a dict comprehension: `m={}\nfor k in ks: m[k]=len(k)`"),
        ("loop_refine", "Fix off-by-one: `for i in range(1,len(a)): print(a[i])` should print all."),
        ("loop_refine", "Add a try/except around `int(s)` returning None on failure."),
        ("loop_refine", "Make this a one-liner: `if x>0:\n return True\nelse:\n return False`"),
    ],
    # (b) mixed real agent session — code + NLP + a couple of hard one-shots
    "B_mixed_session": [
        ("loop_refine", "Fix: `def add(a,b): retrun a+b`. Return only the function."),
        ("simple", "Translate to Spanish: 'The deploy succeeded.'"),
        ("general", "One reason to prefer composition over inheritance?"),
        ("loop_refine", "Add type hints: `def mean(xs): return sum(xs)/len(xs)`"),
        ("simple", "Classify sentiment (pos/neg/neutral): 'this tool wasted my afternoon'"),
        ("interactive", "I'm getting `KeyError: 'id'` from a dict. What are two likely causes?"),
        ("deep_reason", "Prove any comparison sort needs Omega(n log n) worst-case. Decision-tree argument, concise."),
        ("simple", "Extract the URL from: 'docs live at https://ex.com/guide now'"),
        ("general", "Difference between a process and a thread? Two sentences."),
        ("deep_reason", "Design a backpressure strategy for a multi-producer/single-consumer queue that must never drop messages but not OOM. Mechanism and trade-offs."),
    ],
    # (c) reasoning-heavy session
    "C_reasoning": [
        ("deep_reason", "Why is CAP a real trade-off and not a free lunch? Explain with a partition example."),
        ("loop_verify", "Does this satisfy `f(n)=f(n-1)+f(n-2)`? `def f(n): return n if n<2 else f(n-1)+f(n-2)`"),
        ("deep_reason", "Derive the time complexity of binary search and state its recurrence."),
        ("general", "When does eventual consistency become a problem for users? One example."),
        ("deep_reason", "Explain why deadlock needs all four Coffman conditions; remove one and show it breaks."),
        ("loop_verify", "Is this O(n)? `def has_dup(a): return len(a)!=len(set(a))`. Justify."),
        ("deep_reason", "Argue whether a hash table can guarantee O(1) lookup. Address worst case and amortization."),
        ("general", "One concrete reason idempotency matters in a retrying client?"),
        ("deep_reason", "Prove there is no general algorithm to decide if two programs are equivalent. Sketch the reduction."),
    ],
}

# Correctness probes (run separately, each WITH-only unless noted)
PII_PROBE = ("simple", "Summarize: reach Maria at maria.lopez@globex.com or 555-987-6543 re: the refund.")


def get(client, path):
    r = client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


def chat(client, task_type, content, force=None, retries=4):
    hib = {"task_type": task_type}
    if force:
        hib["force"] = force
    body = {"model": "hibrid-auto", "messages": [{"role": "user", "content": content}], "hibrid": hib}
    last = None
    for attempt in range(retries + 1):
        try:
            r = client.post(f"{BASE}/v1/chat/completions", json=body)
        except httpx.TransportError as e:  # connection reset under load
            last = e
            time.sleep(2.0 * (attempt + 1))
            continue
        if r.status_code < 500:
            r.raise_for_status()
            return r.json()
        last = r  # transient 5xx (loaded 2-core box); back off and retry
        time.sleep(2.0 * (attempt + 1))
    if isinstance(last, httpx.Response):
        last.raise_for_status()
    raise last


def row_from(resp, task_type, mode, dt):
    h = resp.get("hibrid", {}) or {}
    chosen = h.get("chosen", {}) or {}
    usage = resp.get("usage", {}) or {}
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    return {
        "task_type": task_type,
        "mode": mode,
        "tier": chosen.get("tier"),
        "model": chosen.get("model"),
        "backend": chosen.get("backend"),
        "escalated": h.get("escalated"),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
        "latency_s": round(dt, 2),
    }


def is_local(r):
    return (r.get("tier") or "") == LOCAL_TIER


def main():
    with httpx.Client(timeout=TIMEOUT) as client:
        node = get(client, "/v1/node")
        metrics_before = get(client, "/v1/metrics")

        # warm-up local model
        try:
            chat(client, "simple", "Say OK.")
        except Exception as e:
            print("warm-up failed (continuing):", e)
        time.sleep(1.0)

        workloads_out = {}
        for wname, tasks in WORKLOADS.items():
            print(f"\n=== Workload {wname} ({len(tasks)} tasks x2 calls) ===")
            pairs = []
            for i, (tt, content) in enumerate(tasks, 1):
                t0 = time.time()
                w = row_from(chat(client, tt, content), tt, "with", time.time() - t0)
                time.sleep(1.0)
                t0 = time.time()
                wo = row_from(chat(client, tt, content, force="cloud_strong"), tt, "without", time.time() - t0)
                time.sleep(1.0)
                pairs.append({"n": i, "task_type": tt, "with": w, "without": wo})
                print(f"  {i:2d} {tt:12s} WITH tier={str(w['tier']):11} esc={w['escalated']} "
                      f"tok={w['total_tokens']:4d} | WITHOUT tier={str(wo['tier']):11} tok={wo['total_tokens']:4d}")
            workloads_out[wname] = pairs

        # correctness probes
        print("\n=== Correctness probes ===")
        t0 = time.time()
        pii = row_from(chat(client, PII_PROBE[0], PII_PROBE[1]), PII_PROBE[0], "with", time.time() - t0)
        print(f"  PII/simple -> tier={pii['tier']} (expect {LOCAL_TIER})")

        metrics_after = get(client, "/v1/metrics")

    # ---- aggregate ----
    def workload_totals(pairs):
        with_local = sum(1 for p in pairs if is_local(p["with"]))
        n = len(pairs)
        f_with = sum(p["with"]["total_tokens"] for p in pairs if not is_local(p["with"]))
        f_without = sum(p["without"]["total_tokens"] for p in pairs)
        any_esc = sum(1 for p in pairs if p["with"]["escalated"])
        return {
            "calls": n,
            "calls_local_with": with_local,
            "pct_calls_local_with": round(100 * with_local / n, 1),
            "escalated_with": any_esc,
            "frontier_tokens_with": f_with,
            "frontier_tokens_without": f_without,
            "frontier_tokens_avoided": f_without - f_with,
            "pct_frontier_tokens_avoided": round(100 * (f_without - f_with) / f_without, 1) if f_without else 0.0,
        }

    per_workload = {w: workload_totals(p) for w, p in workloads_out.items()}
    all_pairs = [p for ps in workloads_out.values() for p in ps]
    overall = workload_totals(all_pairs)

    # by task_type
    by_tt = {}
    for p in all_pairs:
        tt = p["task_type"]
        d = by_tt.setdefault(tt, {"calls": 0, "local_with": 0, "escalated_with": 0,
                                   "frontier_tokens_with": 0, "frontier_tokens_without": 0})
        d["calls"] += 1
        if is_local(p["with"]):
            d["local_with"] += 1
        else:
            d["frontier_tokens_with"] += p["with"]["total_tokens"]
        if p["with"]["escalated"]:
            d["escalated_with"] += 1
        d["frontier_tokens_without"] += p["without"]["total_tokens"]

    correctness = {
        "loop_refine_all_local": {
            "checked": sum(1 for p in all_pairs if p["task_type"] == "loop_refine"),
            "local": sum(1 for p in all_pairs if p["task_type"] == "loop_refine" and is_local(p["with"])),
        },
        "deep_reason_escalates": {
            "checked": sum(1 for p in all_pairs if p["task_type"] == "deep_reason"),
            "escalated": sum(1 for p in all_pairs if p["task_type"] == "deep_reason" and p["with"]["escalated"]),
            "to_frontier": sum(1 for p in all_pairs if p["task_type"] == "deep_reason" and not is_local(p["with"])),
        },
        "pii_simple_stays_local": {"tier": pii["tier"], "pass": pii["tier"] == LOCAL_TIER},
    }

    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "engine": BASE,
        "node": node,
        "methodology": (
            "3 distinct workloads (long refine loop, mixed agent session, reasoning-heavy). "
            "Each task called twice: WITH (auto routing) and WITHOUT (force cloud_strong). "
            "Frontier tokens = tokens of any non-local_free call. Savings = frontier tokens "
            "WITHOUT minus WITH. Strong tier is cli:claude (no per-token $), so unit is "
            "frontier tokens/calls avoided, not dollars."
        ),
        "overall": overall,
        "per_workload": per_workload,
        "by_task_type": by_tt,
        "correctness_checks": correctness,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "workloads": workloads_out,
        "pii_probe": pii,
    }
    (OUT / "agent1_tokenbench.json").write_text(json.dumps(out, indent=2))
    print("\n=== OVERALL ===")
    print(json.dumps(overall, indent=2))
    print("=== CORRECTNESS ===")
    print(json.dumps(correctness, indent=2))


if __name__ == "__main__":
    main()
