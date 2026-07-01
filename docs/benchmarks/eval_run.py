"""eval_run — empirical evaluation harness for the hibrid paper (RQ2 tokens, RQ3 quality,
RQ4 cost/quality Pareto). EVERYTHING is routed THROUGH the hibrid engine to minimise the
orchestrator's own token use:

  - local answer   : POST allow_cloud=false           -> tier=local_free   (FREE, local inference)
  - frontier answer: POST force=cloud_strong          -> tier=paid_strong  (the no-router baseline)
  - judge          : POST force=cloud_strong (rubric) -> blind 0..1 scores of the two answers

The routed (hibrid) path is taken from the routing DECISION (free): if hibrid would keep the
task local, its frontier-token cost is 0 and we reuse the local answer; otherwise it equals the
frontier answer's tokens. This avoids a third execution per task.

Prompts come from eval_prompts.json (the test-design agent's set, aligned with the paper) so the
harness and the article use the SAME workload. Output: eval_results.json.

Run:  .venv/bin/python docs/benchmarks/eval_run.py            # full workload
      .venv/bin/python docs/benchmarks/eval_run.py --limit 4 # smoke test
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend import classifier, router, task_policy  # noqa: E402
from backend.registry import build_node_profile  # noqa: E402
from backend.schemas import ChatMessage, HibridOptions  # noqa: E402

BASE = os.environ.get("HIBRID_BASE", "http://127.0.0.1:8095")
HERE = os.path.dirname(os.path.abspath(__file__))
AXIS_TASK = {"general": "general", "writing": "write", "code": "code",
             "reasoning": "deep_reason", "multilingual": "translate"}


def _refresh():
    try:
        urllib.request.urlopen(urllib.request.Request(BASE + "/v1/node/refresh", data=b"",
                               headers={"Content-Type": "application/json"}), timeout=90)
    except Exception:
        pass


def _post_paid(messages, task_type, timeout=300):
    """Force the paid tier and REQUIRE it actually ran paid (no silent local fallback).
    Retries with a node refresh; raises if a genuine paid answer can't be obtained."""
    for attempt in range(3):
        out = _post(messages, {"task_type": task_type, "force": "cloud_strong"}, timeout=timeout)
        if str(out.get("tier", "")).startswith("paid"):
            return out
        _refresh()  # backend probe was stale/flaky — re-probe and retry
    raise RuntimeError(f"paid tier unavailable (got tier={out.get('tier')}); refuse to use local as frontier")


def _post(messages, hibrid_opts, timeout=240, retries=3):
    body = json.dumps({"model": "hibrid-auto", "messages": messages,
                       "hibrid": hibrid_opts}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                         headers={"Content-Type": "application/json"})
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=timeout))
            dt = time.time() - t0
            break
        except Exception as e:  # noqa: BLE001 — transient 502/timeout: back off and retry
            last = e
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    else:
        raise last
    ch = r.get("hibrid", {}).get("chosen", {})
    usage = r.get("usage", {})
    return {"content": r["choices"][0]["message"]["content"],
            "tier": ch.get("tier"), "model": ch.get("model"),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0), "dt": round(dt, 2)}


JUDGE_SYS = (
    "You are a strict, impartial grader. You will see a task and two candidate answers, A and B, "
    "in random order. Score EACH answer from 0.0 to 1.0 on correctness + completeness + adherence "
    "to the task. Do not assume which model wrote which. Respond with ONLY a JSON object: "
    '{"score_a": <float>, "score_b": <float>, "reason": "<one sentence>"}.'
)


def judge(task, ans_a, ans_b):
    user = (f"TASK:\n{task}\n\n=== ANSWER A ===\n{ans_a}\n\n=== ANSWER B ===\n{ans_b}\n\n"
            "Return only the JSON.")
    out = _post_paid([{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
                     "deep_reason")  # the judge MUST be the paid model, never a local fallback
    txt = out["content"].strip()
    s, e = txt.find("{"), txt.rfind("}")
    data = json.loads(txt[s:e + 1])
    return float(data["score_a"]), float(data["score_b"]), data.get("reason", ""), out


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    prompts = json.load(open(os.path.join(HERE, "eval_prompts.json"), encoding="utf-8"))
    if limit:
        prompts = prompts[:limit]

    _refresh()  # ensure the engine re-probes the paid backend before we start
    import asyncio
    node = asyncio.run(build_node_profile(use_cache=True, benchmark=False))

    rng = random.Random(42)
    rows = []
    for i, p in enumerate(prompts, 1):
        axis, task = p["axis"], p["prompt"]
        tt = AXIS_TASK.get(axis, "general")
        print(f"[{i}/{len(prompts)}] {axis:12} {task[:48]!r}")

        try:
            local = _post([{"role": "user", "content": task}],
                          {"task_type": tt, "allow_cloud": False})
        except Exception as e:
            print(f"      local ERROR: {e}"); continue
        try:
            frontier = _post_paid([{"role": "user", "content": task}], tt)
        except Exception as e:
            print(f"      frontier ERROR (not paid): {e}"); continue

        # hibrid routing DECISION (free): would it keep this local or escalate?
        feat = classifier.classify([ChatMessage(role="user", content=task)])
        dec = router.decide(node, feat, HibridOptions(task_type=tt))
        routed_local = dec.chosen.kind == "local"
        routed_frontier_tokens = 0 if routed_local else frontier["total_tokens"]

        # blind judge in randomized order (N=1 to bound token cost; see threats to validity)
        swap = rng.random() < 0.5
        a, b = (local["content"], frontier["content"]) if not swap else (frontier["content"], local["content"])
        try:
            sa, sb, reason, jout = judge(task, a, b)
            local_score, frontier_score = (sa, sb) if not swap else (sb, sa)
        except Exception as e:
            print(f"      judge ERROR: {e}"); local_score = frontier_score = None; reason = f"judge failed: {e}"

        rows.append({
            "axis": axis, "difficulty": p.get("difficulty", "?"), "prompt": task,
            "local": {**{k: local[k] for k in ("tier", "model", "total_tokens", "dt", "content")},
                      "score": round(local_score, 3) if local_score is not None else None},
            "frontier": {**{k: frontier[k] for k in ("tier", "model", "total_tokens", "dt", "content")},
                         "score": round(frontier_score, 3) if frontier_score is not None else None},
            "routed": {"kind": dec.chosen.kind, "tier": dec.chosen.tier,
                       "model": dec.chosen.model, "frontier_tokens": routed_frontier_tokens,
                       "reason": dec.reason},
            "judge_reason": reason,
        })
        ql = f"{local_score:.2f}" if local_score is not None else "NA"
        qf = f"{frontier_score:.2f}" if frontier_score is not None else "NA"
        print(f"      local={local['tier']}({local['total_tokens']}t, q={ql}) "
              f"frontier={frontier['total_tokens']}t q={qf} routed={dec.chosen.kind}")

    # ---- aggregate ----
    n = len(rows)
    judged = [r for r in rows if r["local"]["score"] is not None and r["frontier"]["score"] is not None]
    nj = len(judged) or 1
    base_tokens = sum(r["frontier"]["total_tokens"] for r in rows)         # always-frontier
    hibrid_tokens = sum(r["routed"]["frontier_tokens"] for r in rows)      # hibrid-routed
    saved_pct = round(100 * (1 - hibrid_tokens / base_tokens), 1) if base_tokens else 0.0
    kept_local = sum(1 for r in rows if r["routed"]["kind"] == "local")
    mean_local_q = round(sum(r["local"]["score"] for r in judged) / nj, 3)
    mean_frontier_q = round(sum(r["frontier"]["score"] for r in judged) / nj, 3)
    parity = sum(1 for r in judged if r["local"]["score"] >= r["frontier"]["score"] - 0.05)

    summary = {
        "n": n,
        "tokens": {"baseline_all_frontier": base_tokens, "hibrid_routed": hibrid_tokens,
                   "frontier_tokens_avoided_pct": saved_pct},
        "routing": {"kept_local": kept_local, "escalated": n - kept_local,
                    "kept_local_pct": round(100 * kept_local / n, 1)},
        "quality": {"mean_local": mean_local_q, "mean_frontier": mean_frontier_q, "n_judged": len(judged),
                    "quality_retained_pct": round(100 * mean_local_q / mean_frontier_q, 1) if mean_frontier_q else 0,
                    "parity_count": parity, "parity_pct": round(100 * parity / nj, 1)},
        "by_axis": {},
    }
    for ax in AXIS_TASK:
        a = [r for r in judged if r["axis"] == ax]
        if a:
            summary["by_axis"][ax] = {
                "n": len(a),
                "mean_local_q": round(sum(r["local"]["score"] for r in a) / len(a), 3),
                "mean_frontier_q": round(sum(r["frontier"]["score"] for r in a) / len(a), 3),
                "kept_local": sum(1 for r in a if r["routed"]["kind"] == "local"),
            }

    out = {"summary": summary, "rows": rows}
    json.dump(out, open(os.path.join(HERE, "eval_results.json"), "w"), indent=2, ensure_ascii=False)
    print("\n==== SUMMARY ====")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n-> {os.path.relpath(os.path.join(HERE, 'eval_results.json'))}")


if __name__ == "__main__":
    main()
