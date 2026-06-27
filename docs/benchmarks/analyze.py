#!/usr/bin/env python3
"""Aggregate the three machines' benchmark JSON + quality judgments into tables and charts.

Inputs : raw/bench_{eu,es,com}.json (from bench.py) and quality.json (judged separately,
         by the orchestration layer — no API key). Outputs: charts/*.png + summary.json.
Run    : python3 analyze.py   (from docs/benchmarks/)
"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CHARTS = os.path.join(HERE, "charts")
os.makedirs(CHARTS, exist_ok=True)

MACHINES = {"eu": "tokenstree.eu (idle)", "es": "tokenstree.es (trading)",
            "com": "tokenstree.com (live primary)"}
BRAND = {"green": "#176043", "rust": "#c2691c", "blue": "#3b5b8c", "slate": "#5b6470"}
COLORS = [BRAND["green"], BRAND["rust"], BRAND["blue"]]


def load():
    data = {}
    for key in MACHINES:
        p = os.path.join(RAW, f"bench_{key}.json")
        if os.path.exists(p):
            data[key] = json.load(open(p, encoding="utf-8"))
    quality = {}
    qp = os.path.join(HERE, "quality.json")
    if os.path.exists(qp):
        quality = json.load(open(qp, encoding="utf-8"))  # {"model|task": score 0..1}
    return data, quality


def chart_tps(data):
    """Mean tok/s per model, grouped by machine."""
    models, per = [], {k: {} for k in data}
    for k, d in data.items():
        for r in d["results"]:
            if "tok_s" in r:
                per[k].setdefault(r["model"], []).append(r["tok_s"])
            if r["model"] not in models:
                models.append(r["model"])
    models = sorted(models, key=lambda m: (("0.5" not in m), ("1.5" not in m), m))
    fig, ax = plt.subplots(figsize=(10, 5))
    n = len(data); w = 0.8 / max(1, n)
    for i, (k, d) in enumerate(data.items()):
        ys = [round(sum(per[k][m]) / len(per[k][m]), 1) if per[k].get(m) else 0 for m in models]
        xs = [j + i * w for j in range(len(models))]
        ax.bar(xs, ys, width=w, label=MACHINES[k], color=COLORS[i % 3])
        for x, y in zip(xs, ys):
            if y:
                ax.text(x, y + 0.4, str(y), ha="center", va="bottom", fontsize=7)
    ax.set_xticks([j + 0.4 - w / 2 for j in range(len(models))])
    ax.set_xticklabels(models, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("tokens / second (measured, CPU-only)")
    ax.set_title("Real local throughput per model × machine")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(CHARTS, "tps.png"), dpi=130); plt.close(fig)


def chart_quality_by_axis(data, quality):
    """Mean judged quality per model per task axis (uses one machine's outputs; quality is
    machine-independent at temperature 0)."""
    axes = ["general", "code", "reasoning"]
    # gather models seen anywhere
    models = []
    for d in data.values():
        for r in d["results"]:
            if r["model"] not in models:
                models.append(r["model"])
    models = sorted(models, key=lambda m: float(_size(m)))
    fig, ax = plt.subplots(figsize=(10, 5))
    w = 0.25
    for ai, axis in enumerate(axes):
        ys = []
        for m in models:
            scores = [quality.get(f"{m}|{r['task']}") for d in data.values() for r in d["results"]
                      if r["model"] == m and r.get("axis") == axis and quality.get(f"{m}|{r['task']}") is not None]
            ys.append(round(sum(scores) / len(scores), 2) if scores else 0)
        xs = [j + ai * w for j in range(len(models))]
        ax.bar(xs, ys, width=w, label=axis, color=[BRAND["slate"], BRAND["rust"], BRAND["blue"]][ai])
    ax.set_xticks([j + w for j in range(len(models))])
    ax.set_xticklabels(models, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("judged quality (0–1)"); ax.set_ylim(0, 1.05)
    ax.set_title("Local-model quality by task axis (judged by the strong tier, no API key)")
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(CHARTS, "quality_axis.png"), dpi=130); plt.close(fig)


def chart_local_parity(data, quality, threshold=0.7):
    """% of tasks each machine can serve locally at parity (best local model quality ≥ threshold)."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels, vals = [], []
    for k, d in data.items():
        by_task = {}
        for r in d["results"]:
            q = quality.get(f"{r['model']}|{r.get('task')}")
            if q is not None:
                by_task.setdefault(r["task"], []).append(q)
        if not by_task:
            continue
        ok = sum(1 for t, qs in by_task.items() if max(qs) >= threshold)
        labels.append(MACHINES[k]); vals.append(round(100 * ok / len(by_task)))
    bars = ax.barh(labels, vals, color=COLORS[:len(labels)])
    for b, v in zip(bars, vals):
        ax.text(v + 1, b.get_y() + b.get_height() / 2, f"{v}%", va="center", fontsize=9)
    ax.set_xlim(0, 100); ax.set_xlabel(f"% tasks solved locally at parity (quality ≥ {threshold})")
    ax.set_title("How much each machine keeps off the paid tier")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(CHARTS, "local_parity.png"), dpi=130); plt.close(fig)


def _size(model):
    import re
    m = re.search(r"(\d+\.?\d*)b", model.lower())
    return m.group(1) if m else "7"


def main():
    data, quality = load()
    if not data:
        print("no raw data yet"); return
    chart_tps(data)
    if quality:
        chart_quality_by_axis(data, quality)
        chart_local_parity(data, quality)
    # summary.json
    summary = {"machines": {}}
    for k, d in data.items():
        tps = [r["tok_s"] for r in d["results"] if "tok_s" in r]
        summary["machines"][k] = {
            "label": MACHINES[k], "profile": d["machine"],
            "models": sorted({r["model"] for r in d["results"]}),
            "mean_tok_s": round(sum(tps) / len(tps), 1) if tps else 0,
            "n_calls": len(tps)}
    json.dump(summary, open(os.path.join(HERE, "summary.json"), "w"), indent=2, ensure_ascii=False)
    print("charts + summary written")


if __name__ == "__main__":
    main()
