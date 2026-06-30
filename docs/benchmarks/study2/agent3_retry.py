#!/usr/bin/env python3
"""Re-run the probes that hit transient 502s under load."""
import json, os, time
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:8095"
OUT = Path(__file__).resolve().parent
TIMEOUT = httpx.Timeout(180.0)


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


def extract(resp):
    h = resp.get("hibrid", {}); c = h.get("chosen", {})
    u = resp.get("usage", {}) or {}
    pt = int(u.get("prompt_tokens", 0) or 0); ct = int(u.get("completion_tokens", 0) or 0)
    try: msg = resp["choices"][0]["message"]["content"]
    except Exception: msg = ""
    return {"tier": c.get("tier"), "kind": c.get("kind"), "model": c.get("model"),
            "escalated": h.get("escalated"), "reason": h.get("reason"),
            "total_tokens": pt + ct, "answer": msg}


JOBS = [
    ("batch_local", "Summarize in one sentence: 'The router keeps cheap calls local and escalates hard ones.'", {"task_type": "batch"}),
    ("pii_phone_ssn_local", "Here is the record 123-45-6789. Prove the theorem step by step and analyze its complexity in depth.", {"task_type": "deep_reason"}),
    ("force_local", "Design a distributed architecture and analyze the trade-offs step by step.", {"task_type": "deep_reason", "force": "local"}),
    ("svq_listcomp_auto", "Refactor to a single list comprehension: `out=[]\nfor x in xs:\n    if x>0: out.append(x*x)`", {"task_type": "loop_refine"}),
]

out = {}
with httpx.Client(timeout=TIMEOUT) as client:
    for jid, prompt, opts in JOBS:
        t0 = time.time()
        try:
            e = extract(chat(client, prompt, opts)); err = None
        except Exception as ex:
            e = {}; err = str(ex)
        dt = round(time.time() - t0, 2)
        e["latency_s"] = dt; e["error"] = err
        out[jid] = e
        print(f"  {jid:22s} tier={e.get('tier')} kind={e.get('kind')} tok={e.get('total_tokens')} {dt}s err={err}")
        if e.get("answer"):
            print("    ans:", e["answer"][:120].replace("\n", " "))
        time.sleep(2.0)

(OUT / "agent3_retry.json").write_text(json.dumps(out, indent=2))
print("wrote agent3_retry.json")
