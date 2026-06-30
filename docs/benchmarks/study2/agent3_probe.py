#!/usr/bin/env python3
"""QualityGuard probes: routing-decision correctness + savings-vs-quality.

Imitates token_savings_run.py: warm-up, retry-on-5xx, sleep between calls,
180s timeout. Writes raw results to agent3_raw.json for analysis.
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


def get(client, path):
    r = client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


def chat(client, content, hibrid_opts, retries=2):
    body = {
        "model": "hibrid-auto",
        "messages": [{"role": "user", "content": content}],
        "hibrid": hibrid_opts,
    }
    last = None
    for attempt in range(retries + 1):
        r = client.post(f"{BASE}/v1/chat/completions", json=body)
        if r.status_code < 500:
            r.raise_for_status()
            return r.json()
        last = r
        time.sleep(1.5 * (attempt + 1))
    last.raise_for_status()


def extract(resp):
    h = resp.get("hibrid", {})
    chosen = h.get("chosen", {})
    usage = resp.get("usage", {}) or h.get("usage", {}) or {}
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    msg = ""
    try:
        msg = resp["choices"][0]["message"]["content"]
    except Exception:
        msg = ""
    return {
        "tier": chosen.get("tier"),
        "kind": chosen.get("kind"),
        "model": chosen.get("model"),
        "backend": chosen.get("backend"),
        "escalated": h.get("escalated"),
        "reason": h.get("reason"),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
        "answer": msg,
    }


# --- 1. CORRECTNESS MATRIX ---
# (rule_id, description, prompt, hibrid_opts, expected_tier, expected_kind)
CORRECTNESS = [
    ("simple_local", "simple task stays local_free",
     "Translate to Spanish: 'The build is green.'",
     {"task_type": "simple"}, "local_free", "local"),
    ("loop_refine_local", "loop_refine stays local_free",
     "Fix this Python: `def add(a, b): retrun a + b`. Return only the corrected function.",
     {"task_type": "loop_refine"}, "local_free", "local"),
    ("batch_local", "batch stays local_free",
     "Summarize in one sentence: 'The router keeps cheap calls local and escalates hard ones.'",
     {"task_type": "batch"}, "local_free", "local"),
    ("loop_refine_complex_local", "loop_refine never jumps to strong even if complex",
     "Loop: refactor and fix all bugs iteratively until the lint passes for this module.",
     {"task_type": "loop_refine"}, None, "local"),  # expect local_free or paid_cheap, never strong
    ("deep_reason_escalates", "deep_reason hard one-shot allowed to escalate",
     "Prove that any comparison-based sort needs Omega(n log n) comparisons in the worst "
     "case. Give the decision-tree argument concisely and derive the bound step by step.",
     {"task_type": "deep_reason"}, None, None),  # expect paid tier (escalation allowed)
    ("pii_email_local", "PII email forces local regardless of deep_reason",
     "My email is juan.perez@example.com. Design a distributed architecture and analyze "
     "the consistency trade-offs step by step, deriving the complexity.",
     {"task_type": "deep_reason"}, "local_free", "local"),
    ("pii_phone_ssn_local", "PII SSN-like number forces local",
     "Here is the record 123-45-6789. Prove the theorem step by step and analyze its "
     "complexity in depth.",
     {"task_type": "deep_reason"}, "local_free", "local"),
    ("pii_card_local", "PII credit-card-like number forces local",
     "Charge card 4111 1111 1111 1111. Design the optimal algorithm and derive the bound.",
     {"task_type": "deep_reason"}, "local_free", "local"),
    ("allow_cloud_false_local", "allow_cloud=False on a hard task stays local",
     "Design a distributed consensus protocol and prove its safety and liveness step by step.",
     {"task_type": "deep_reason", "allow_cloud": False}, "local_free", "local"),
    ("force_strong", "force cloud_strong honored",
     "Hello there.",
     {"force": "cloud_strong"}, "paid_strong", "cloud_strong"),
    ("force_local", "force local honored on a hard task",
     "Design a distributed architecture and analyze the trade-offs step by step.",
     {"task_type": "deep_reason", "force": "local"}, "local_free", "local"),
    ("force_cloud_cheap", "force cloud_cheap honored",
     "Hi.",
     {"force": "cloud_cheap"}, "paid_cheap", "cloud_cheap"),
]


# --- 2. SAVINGS-VS-QUALITY ---
# Tasks that should stay local under auto; compare auto (local) vs forced strong.
# checker returns ("ok"/"bad"/"manual", note) given the answer text.
def chk_contains(*subs):
    def f(ans):
        a = ans.lower()
        hit = [s for s in subs if s.lower() in a]
        return ("ok" if hit else "manual", f"matched={hit}")
    return f


SVQ = [
    ("svq_typo", "loop_refine", "Fix this Python: `def add(a, b): retrun a + b`. Return only the corrected function.",
     chk_contains("return a + b", "return a+b")),
    ("svq_listcomp", "loop_refine", "Refactor to a single list comprehension: `out=[]\nfor x in xs:\n    if x>0: out.append(x*x)`",
     chk_contains("[x*x for x in xs if x", "for x in xs if x>0", "for x in xs if x > 0")),
    ("svq_reverse", "loop_refine", "This test fails: `assert reverse('abc')=='cba'`. Write the `reverse` function.",
     chk_contains("[::-1]", "reversed(")),
    ("svq_translate", "simple", "Translate to Spanish: 'The build is green.'",
     chk_contains("verde", "compilaci", "build")),
    ("svq_sentiment", "simple", "Classify sentiment as exactly one word (positive/negative/neutral): 'this library saved me hours'",
     chk_contains("positive", "positiv")),
    ("svq_summary", "simple", "Summarize in one sentence: 'The router keeps cheap calls local and only escalates hard ones.'",
     chk_contains("local", "escalat", "cheap", "router")),
]


def main():
    results = {"base": BASE, "correctness": [], "svq": [], "node": None, "policy": None,
               "metrics_before": None, "metrics_after": None,
               "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
    with httpx.Client(timeout=TIMEOUT) as client:
        results["node"] = get(client, "/v1/node")
        results["policy"] = get(client, "/v1/policy")
        results["metrics_before"] = get(client, "/v1/metrics")

        # warm-up
        print("warm-up...")
        try:
            chat(client, "Say OK.", {"task_type": "simple"})
        except Exception as e:
            print("warm-up failed:", e)
        time.sleep(1.0)

        print("\n=== CORRECTNESS ===")
        for rid, desc, prompt, opts, exp_tier, exp_kind in CORRECTNESS:
            t0 = time.time()
            try:
                resp = chat(client, prompt, opts)
                e = extract(resp)
                err = None
            except Exception as ex:
                e = {}
                err = str(ex)
            dt = round(time.time() - t0, 2)
            row = {"rule": rid, "desc": desc, "opts": opts,
                   "expected_tier": exp_tier, "expected_kind": exp_kind,
                   "observed_tier": e.get("tier"), "observed_kind": e.get("kind"),
                   "observed_model": e.get("model"), "escalated": e.get("escalated"),
                   "reason": e.get("reason"), "latency_s": dt, "error": err}
            results["correctness"].append(row)
            print(f"  {rid:26s} -> tier={str(e.get('tier')):11} kind={str(e.get('kind')):12} {dt}s err={err}")
            time.sleep(1.0)

        print("\n=== SAVINGS VS QUALITY ===")
        for sid, tt, prompt, checker in SVQ:
            # auto
            t0 = time.time()
            try:
                ra = chat(client, prompt, {"task_type": tt})
                ea = extract(ra)
                erra = None
            except Exception as ex:
                ea = {}; erra = str(ex)
            dta = round(time.time() - t0, 2)
            time.sleep(1.0)
            # forced strong
            t0 = time.time()
            try:
                rs = chat(client, prompt, {"task_type": tt, "force": "cloud_strong"})
                es = extract(rs)
                errs = None
            except Exception as ex:
                es = {}; errs = str(ex)
            dts = round(time.time() - t0, 2)

            auto_ans = ea.get("answer", "") or ""
            strong_ans = es.get("answer", "") or ""
            ac = checker(auto_ans) if auto_ans else ("bad", "no answer")
            sc = checker(strong_ans) if strong_ans else ("bad", "no answer")
            row = {
                "id": sid, "task_type": tt, "prompt": prompt,
                "auto": {"tier": ea.get("tier"), "kind": ea.get("kind"), "model": ea.get("model"),
                         "total_tokens": ea.get("total_tokens"), "latency_s": dta,
                         "answer": auto_ans, "check": ac[0], "check_note": ac[1], "error": erra},
                "strong": {"tier": es.get("tier"), "kind": es.get("kind"), "model": es.get("model"),
                           "total_tokens": es.get("total_tokens"), "latency_s": dts,
                           "answer": strong_ans, "check": sc[0], "check_note": sc[1], "error": errs},
            }
            results["svq"].append(row)
            print(f"  {sid:16s} auto[{str(ea.get('tier')):10} chk={ac[0]:6} tok={ea.get('total_tokens')}] "
                  f"strong[{str(es.get('tier')):10} chk={sc[0]:6} tok={es.get('total_tokens')}]")
            time.sleep(1.0)

        results["metrics_after"] = get(client, "/v1/metrics")

    (OUT / "agent3_raw.json").write_text(json.dumps(results, indent=2))
    print("\nwrote", OUT / "agent3_raw.json")
    return results


if __name__ == "__main__":
    main()
