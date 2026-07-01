"""eval_charts — figures for the hibrid evaluation paper, from eval_results.json (+ optional
competitors.json for the related-work comparison). Saves PNGs to docs/benchmarks/img/.

Run:  .venv/bin/python docs/benchmarks/eval_charts.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
os.makedirs(IMG, exist_ok=True)
BR = {"green": "#176043", "rust": "#c2691c", "blue": "#3b5b8c", "slate": "#5b6470", "lite": "#9ec6b4"}
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 130})


def load(name):
    p = os.path.join(HERE, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def fig_tokens(data):
    """Figure 1: frontier tokens — all-frontier baseline vs all-local (measured bound)."""
    rows = [r for r in data["rows"] if r["frontier"]["score"] is not None]
    base = sum(r["frontier"]["total_tokens"] for r in rows)
    fig, ax = plt.subplots(figsize=(5.2, 4))
    bars = ax.bar(["No router\n(all frontier)", "hibrid\n(all local)"],
                  [base, 0], color=[BR["slate"], BR["green"]], width=0.55)
    ax.set_ylabel("frontier tokens (workload total)")
    ax.set_title(f"Frontier tokens: 100% avoided  (n={len(rows)})")
    for b, v in zip(bars, [base, 0]):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,}", ha="center", va="bottom")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "eval_tokens.png")); plt.close(fig)


def fig_quality(s):
    """Figure 2: mean quality local vs frontier, overall and per axis."""
    axes_order = [a for a in ["general", "writing", "code", "reasoning", "multilingual"]
                  if a in s["by_axis"]]
    labels = ["overall"] + axes_order
    loc = [s["quality"]["mean_local"]] + [s["by_axis"][a]["mean_local_q"] for a in axes_order]
    fro = [s["quality"]["mean_frontier"]] + [s["by_axis"][a]["mean_frontier_q"] for a in axes_order]
    x = range(len(labels)); w = 0.38
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.bar([i - w / 2 for i in x], loc, w, label="local (free)", color=BR["green"])
    ax.bar([i + w / 2 for i in x], fro, w, label="frontier (paid)", color=BR["slate"])
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("blind judge score (0–1)"); ax.set_ylim(0, 1.05)
    ax.set_title(f"Quality retained: {s['quality']['quality_retained_pct']}% "
                 f"(local {s['quality']['mean_local']} vs frontier {s['quality']['mean_frontier']})")
    ax.legend(); fig.tight_layout(); fig.savefig(os.path.join(IMG, "eval_quality.png")); plt.close(fig)


def fig_pareto(data):
    """Figure 3: cost/quality trade-off — all-local vs all-frontier (measured, judged rows)."""
    rows = [r for r in data["rows"] if r["frontier"]["score"] is not None
            and r["local"]["score"] is not None]
    n = len(rows)
    all_local_q = round(sum(r["local"]["score"] for r in rows) / n, 3)
    all_frontier_q = round(sum(r["frontier"]["score"] for r in rows) / n, 3)
    all_frontier_tokens = sum(r["frontier"]["total_tokens"] for r in rows)
    pts = [("all-local (free)", 0, all_local_q, BR["green"]),
           ("all-frontier (paid)", all_frontier_tokens, all_frontier_q, BR["slate"])]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    for name, x, y, c in pts:
        ax.scatter(x, y, s=150, color=c, zorder=3)
        ax.annotate(f"{name}\n({x:,}t, q={y})", (x, y), textcoords="offset points",
                    xytext=(8, -4), fontsize=9)
    ax.plot([p[1] for p in pts], [p[2] for p in pts], color=BR["slate"], alpha=0.3, zorder=1)
    ax.set_xlabel("frontier tokens (workload total) — cost")
    ax.set_ylabel("mean quality, blind judge (0–1)")
    ax.set_title(f"100% of frontier tokens saved for {round((1-all_local_q/all_frontier_q)*100,1)}% quality drop (n={n})")
    ax.set_ylim(min(all_local_q, all_frontier_q) - 0.08, 1.0)
    ax.set_xlim(-max(all_frontier_tokens * 0.15, 200), all_frontier_tokens * 1.25)
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "eval_pareto.png")); plt.close(fig)


def fig_competitors(comp):
    """Figure 4 (optional): reported cost saving by tool. REPORTED numbers, not measured here."""
    rows = [c for c in comp.get("tools", []) if c.get("cost_saving_pct") is not None]
    if not rows:
        return
    rows.sort(key=lambda c: c["cost_saving_pct"])
    names = [c["name"] for c in rows]; vals = [c["cost_saving_pct"] for c in rows]
    cols = [BR["green"] if c["name"].lower().startswith("hibrid") else BR["slate"] for c in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(names, vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v}%", va="center")
    ax.set_xlabel("reported cost / token saving (%) — authors' own conditions, not comparable")
    ax.set_title("Reported savings across routers (literature)")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "eval_competitors.png")); plt.close(fig)


def main():
    data = load("eval_results.json")
    made = []
    if data:
        s = data["summary"]
        fig_tokens(data); made.append("eval_tokens.png")
        fig_quality(s); made.append("eval_quality.png")
        fig_pareto(data); made.append("eval_pareto.png")
    comp = load("competitors.json")
    if comp:
        fig_competitors(comp); made.append("eval_competitors.png")
    print("charts ->", ", ".join(os.path.join("docs/benchmarks/img", m) for m in made) or "(no inputs)")


if __name__ == "__main__":
    main()
