"""eval_routing_sweep — RQ2/RQ4 across hardware tiers, token-free.

Quality (RQ3) is measured once on the real node (a 3B model — worst case). Token efficiency
depends on what local models a node can hold, so we evaluate the ROUTING DECISION (free, no
inference) for the same 16 prompts on four synthetic machine profiles, and turn it into
Frontier-Tokens-Avoided using the *measured* per-prompt frontier token counts from eval_results.json.

    FTA%(machine) = 1 − Σ_escalated frontier_tokens / Σ_all frontier_tokens

Run after eval_run.py:  .venv/bin/python docs/benchmarks/eval_routing_sweep.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend import classifier, router  # noqa: E402
from backend.backends import Backend  # noqa: E402
from backend.profiler import HardwareProfile  # noqa: E402
from backend.registry import NodeProfile  # noqa: E402
from backend.schemas import ChatMessage, HibridOptions  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AXIS_TASK = {"general": "general", "writing": "write", "code": "code",
             "reasoning": "deep_reason", "multilingual": "translate"}


def _node(ram, gpu, vram, maxp, local, tps):
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="t", cpu_cores_physical=8, ram_gb=ram,
                         gpu_vendor=gpu, gpu_name="g", vram_gb=vram, apple_silicon=False,
                         machine_class="t", max_local_params_b=maxp)
    n = NodeProfile(hw)
    n.local_endpoint = "http://x"; n.local_models = local; n.local_default = local[0]
    n.tok_s = {m: tps for m in local}
    n.cloud_models = ["claude-opus-4-8", "claude-haiku-4-5-20251001"]
    n.backends = [Backend(id="cli:claude", mechanism="cli", agent="claude",
                          models=n.cloud_models, available=True, latency_s=2.5)]
    return n


MACHINES = {
    "cpu_small (8GB)":  _node(8, "none", 0, 3.0, ["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "llama3.2:3b", "qwen3:4b"], 8),
    "cpu_large (32GB)": _node(32, "none", 0, 7.0, ["qwen2.5-coder:7b", "qwen3:8b", "aya-expanse:8b", "deepseek-r1:7b"], 12),
    "gpu_12gb":         _node(32, "nvidia", 12, 8.0, ["qwen2.5-coder:7b", "qwen3:8b", "aya-expanse:8b", "deepseek-r1:8b"], 45),
    "gpu_24gb":         _node(64, "nvidia", 24, 33.0, ["qwen2.5-coder:32b", "qwen2.5:14b", "qwen3:14b", "phi4-reasoning:14b", "aya-expanse:8b"], 90),
}


def main():
    ev = json.load(open(os.path.join(HERE, "eval_results.json"), encoding="utf-8"))
    ftokens = {r["prompt"]: r["frontier"]["total_tokens"] for r in ev["rows"]}
    prompts = json.load(open(os.path.join(HERE, "eval_prompts.json"), encoding="utf-8"))
    prompts = [p for p in prompts if p["prompt"] in ftokens]  # only judged ones
    total_ft = sum(ftokens[p["prompt"]] for p in prompts) or 1

    out = {"machines": {}, "n": len(prompts), "baseline_frontier_tokens": total_ft}
    for mname, node in MACHINES.items():
        kept = 0; escalated_ft = 0; per_axis = {}
        for p in prompts:
            tt = AXIS_TASK.get(p["axis"], "general")
            feat = classifier.classify([ChatMessage(role="user", content=p["prompt"])])
            dec = router.decide(node, feat, HibridOptions(task_type=tt))
            local = dec.chosen.kind == "local"
            kept += local
            if not local:
                escalated_ft += ftokens[p["prompt"]]
            d = per_axis.setdefault(p["axis"], [0, 0])
            d[0] += 1; d[1] += local
        out["machines"][mname] = {
            "kept_local": kept, "kept_local_pct": round(100 * kept / len(prompts), 1),
            "frontier_tokens": escalated_ft,
            "fta_pct": round(100 * (1 - escalated_ft / total_ft), 1),
            "by_axis_kept": {a: f"{v[1]}/{v[0]}" for a, v in per_axis.items()},
        }
    json.dump(out, open(os.path.join(HERE, "routing_sweep.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
