#!/usr/bin/env python3
"""Before/after measurement of frontier-tier token consumption avoided by the
hibrid router. Runs a realistic agent-session workload against a local hibrid
engine where the strong tier (cli:claude) is authenticated, so escalations
actually execute.

Honest methodology: the "paid" strong tier here is the user's Claude
subscription via cli:claude — there is NO per-token dollar price, so the saving
is expressed as FRONTIER-TIER TOKENS / CALLS AVOIDED, not dollars. Token counts
come from each response's `usage` block. Small suite; local model is a 1-3B
class model. See token_savings.md for caveats.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

BASE = os.getenv("HIBRID_BASE", "http://127.0.0.1:8095")
OUT = Path(__file__).resolve().parent
TIMEOUT = httpx.Timeout(180.0)

# Realistic agent-session workload: code refine loop + light NLP + a couple of
# genuinely hard one-shot reasoning calls (these are the ones meant to escalate).
WORKLOAD = [
    # 8 loop_refine — small code fixes/refactors (the bread and butter of an agent loop)
    ("loop_refine", "Fix this Python: `def add(a, b): retrun a + b`. Return only the corrected function."),
    ("loop_refine", "Refactor to a list comprehension: `out=[]\nfor x in xs:\n    if x>0: out.append(x*x)`"),
    ("loop_refine", "Add a docstring to: `def slug(s): return s.lower().replace(' ', '-')`"),
    ("loop_refine", "This test fails: `assert reverse('abc')=='cba'`. Write `reverse`."),
    ("loop_refine", "Rename variable `l` to something readable: `l=[1,2,3]; print(sum(l))`"),
    ("loop_refine", "Add type hints: `def mean(xs): return sum(xs)/len(xs)`"),
    ("loop_refine", "Guard against division by zero in: `def mean(xs): return sum(xs)/len(xs)`"),
    ("loop_refine", "Convert this to use f-string: `print('hi ' + name + '!')`"),
    # 4 simple — translate/classify/extract/summarize
    ("simple", "Translate to Spanish: 'The build is green.'"),
    ("simple", "Classify sentiment (positive/negative/neutral): 'this library saved me hours'"),
    ("simple", "Extract the email from: 'ping me at sam@example.com tomorrow'"),
    ("simple", "Summarize in one sentence: 'The router keeps cheap calls local and only escalates hard ones.'"),
    # 2 general
    ("general", "What is the difference between a process and a thread? Two sentences."),
    ("general", "Give one reason to prefer composition over inheritance."),
    # 2 deep_reason — genuinely hard one-shots; these should hit the strong tier
    ("deep_reason", "Design a backpressure strategy for a multi-producer/single-consumer queue that must never drop messages but also must not OOM. Explain the mechanism and the trade-offs."),
    ("deep_reason", "Prove that any comparison-based sort needs Omega(n log n) comparisons in the worst case. Give the decision-tree argument concisely."),
]


def get(client, path):
    r = client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


def chat(client, task_type, content, retries=2):
    body = {
        "model": "hibrid-auto",
        "messages": [{"role": "user", "content": content}],
        "hibrid": {"task_type": task_type},
    }
    last = None
    for attempt in range(retries + 1):
        r = client.post(f"{BASE}/v1/chat/completions", json=body)
        if r.status_code < 500:
            r.raise_for_status()
            return r.json()
        last = r  # transient backend hiccup (e.g. Ollama disconnect); retry
        time.sleep(1.5 * (attempt + 1))
    last.raise_for_status()


def main():
    with httpx.Client(timeout=TIMEOUT) as client:
        before = get(client, "/v1/metrics")
        calls = []
        for i, (tt, content) in enumerate(WORKLOAD, 1):
            t0 = time.time()
            resp = chat(client, tt, content)
            dt = time.time() - t0
            h = resp.get("hibrid", {})
            chosen = h.get("chosen", {})
            usage = resp.get("usage", {}) or h.get("usage", {}) or {}
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)
            row = {
                "n": i,
                "task_type": tt,
                "tier": chosen.get("tier"),
                "kind": chosen.get("kind"),
                "model": chosen.get("model"),
                "backend": chosen.get("backend"),
                "escalated": h.get("escalated"),
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": pt + ct,
                "latency_s": round(dt, 2),
            }
            calls.append(row)
            print(f"  {i:2d} {tt:12s} -> tier={row['tier']:11} model={str(row['model'])[:24]:24} "
                  f"esc={row['escalated']} tok={row['total_tokens']:4d} {dt:5.1f}s")
            time.sleep(1.0)
        after = get(client, "/v1/metrics")

    def is_paid(r):
        return (r["tier"] or "").startswith("paid") or r["tier"] not in (None, "local_free")

    total = len(calls)
    local_calls = [r for r in calls if (r["tier"] or "") == "local_free"]
    paid_calls = [r for r in calls if is_paid(r)]
    frontier_with = sum(r["total_tokens"] for r in paid_calls)
    frontier_without = sum(r["total_tokens"] for r in calls)  # if EVERY call went frontier
    tokens_avoided = frontier_without - frontier_with
    pct_local = round(100 * len(local_calls) / total, 1)
    pct_tokens_avoided = round(100 * tokens_avoided / frontier_without, 1) if frontier_without else 0.0

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "engine": BASE,
        "node": {"machine_class": "cpu_8gb", "local_model_class": "1-3B (llama3.2:3b / qwen2.5-coder:1.5b)"},
        "methodology": (
            "Realistic agent-session workload through hibrid. Strong tier is the "
            "user's Claude subscription via cli:claude (no per-token price), so "
            "savings are expressed as frontier-tier TOKENS and CALLS avoided, not "
            "dollars. Token counts taken from each response's usage block. "
            "'Frontier tokens WITHOUT hibrid' is the counterfactual where every "
            "call had been sent to the frontier model."
        ),
        "totals": {
            "total_calls": total,
            "local_calls": len(local_calls),
            "paid_calls": len(paid_calls),
            "pct_calls_kept_local": pct_local,
            "frontier_tokens_with_hibrid": frontier_with,
            "frontier_tokens_without_hibrid": frontier_without,
            "frontier_tokens_avoided": tokens_avoided,
            "pct_frontier_tokens_avoided": pct_tokens_avoided,
        },
        "by_task_type": {},
        "metrics_before": before,
        "metrics_after": after,
        "calls": calls,
    }
    for tt in ("loop_refine", "simple", "general", "deep_reason"):
        rows = [r for r in calls if r["task_type"] == tt]
        if not rows:
            continue
        summary["by_task_type"][tt] = {
            "calls": len(rows),
            "local": sum(1 for r in rows if (r["tier"] or "") == "local_free"),
            "paid": sum(1 for r in rows if is_paid(r)),
            "tokens": sum(r["total_tokens"] for r in rows),
        }

    (OUT / "token_savings.json").write_text(json.dumps(summary, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary["totals"], indent=2))
    return summary


if __name__ == "__main__":
    main()
