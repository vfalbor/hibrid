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


def _strategies(data):
    """Three operating points over judged rows: without-hibrid (all paid), hibrid
    (route by task difficulty: trivial->local free, hard->paid), all-local."""
    rows = [r for r in data["rows"] if r["local"]["score"] is not None
            and r["frontier"]["score"] is not None]
    triv = [r for r in rows if r["difficulty"] == "trivial"]
    hard = [r for r in rows if r["difficulty"] == "hard"]
    n = len(rows)
    base_tok = sum(r["frontier"]["total_tokens"] for r in rows)
    base_q = sum(r["frontier"]["score"] for r in rows) / n
    hib_tok = sum(r["frontier"]["total_tokens"] for r in hard)
    hib_q = (sum(r["local"]["score"] for r in triv) + sum(r["frontier"]["score"] for r in hard)) / n
    loc_q = sum(r["local"]["score"] for r in rows) / n
    return {"n": n, "base": (base_tok, base_q), "hibrid": (hib_tok, round(hib_q, 3)),
            "local": (0, round(loc_q, 3))}


def fig_tokens(data):
    """Figure 1: paid tokens by strategy (without hibrid / hibrid routed / all local)."""
    st = _strategies(data)
    labels = ["Without hibrid\n(all paid)", "hibrid\n(route by task)", "All local\n(3B only)"]
    vals = [st["base"][0], st["hibrid"][0], st["local"][0]]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, vals, color=[BR["slate"], BR["green"], BR["lite"]], width=0.6)
    ax.set_ylabel("paid (frontier) tokens — workload total")
    saved = round(100 * (1 - st["hibrid"][0] / st["base"][0]), 1)
    ax.set_title(f"Paid tokens: hibrid saves {saved}% on this one-shot mix (n={st['n']})")
    for b, v in zip(bars, vals):
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
    """Figure 3: cost/quality — without hibrid, hibrid (routed), all-local (judged rows)."""
    st = _strategies(data)
    pts = [("all local (3B)", st["local"][0], st["local"][1], BR["lite"]),
           ("hibrid (route by task)", st["hibrid"][0], st["hibrid"][1], BR["green"]),
           ("without hibrid (all paid)", st["base"][0], st["base"][1], BR["slate"])]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for name, x, y, c in pts:
        ax.scatter(x, y, s=150, color=c, zorder=3)
        ax.annotate(f"{name}\n({x:,}t, q={y})", (x, y), textcoords="offset points",
                    xytext=(8, -6), fontsize=9)
    xs = [p[1] for p in pts]; ys = [p[2] for p in pts]
    ax.plot(xs, ys, color=BR["slate"], alpha=0.3, zorder=1)
    ax.set_xlabel("paid (frontier) tokens — cost")
    ax.set_ylabel("mean quality, blind judge (0–1)")
    kept = round(100 * st["hibrid"][1] / st["base"][1], 1)
    ax.set_title(f"hibrid keeps {kept}% of frontier quality below the all-paid cost (n={st['n']})")
    ax.set_ylim(min(ys) - 0.08, 1.0)
    ax.set_xlim(-max(max(xs) * 0.12, 200), max(xs) * 1.3)
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
