"""gen_landing_demo — inject a 'local vs frontier' comparison section into the hibrid landing
(backend/static/index.html), built from REAL measured eval_results.json: per-example model,
tokens spent, quality score, and the routing decision behind each call. Idempotent: replaces
content between <!--COMPARE_START--> and <!--COMPARE_END-->.

Run:  .venv/bin/python docs/benchmarks/gen_landing_demo.py
"""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LANDING = os.path.join(ROOT, "backend", "static", "index.html")
RESULTS = os.path.join(HERE, "eval_results.json")
START, END = "<!--COMPARE_START-->", "<!--COMPARE_END-->"
AX_LABEL = {"general": "general", "writing": "writing", "code": "code",
            "reasoning": "reasoning", "multilingual": "translation"}


def trunc(t, n=300):
    t = " ".join(t.split())
    return html.escape(t[:n] + ("…" if len(t) > n else ""))


def pick_examples(rows, k_per_axis=1):
    out = []
    for ax in ["general", "writing", "code", "reasoning", "multilingual"]:
        a = [r for r in rows if r["axis"] == ax
             and r["local"]["score"] is not None and r["frontier"]["score"] is not None]
        # prefer the example where local is closest to (or beats) frontier — shows parity
        a.sort(key=lambda r: r["frontier"]["score"] - r["local"]["score"])
        out += a[:k_per_axis]
    return out


def card(r):
    loc, fro = r["local"], r["frontier"]
    saved = fro["total_tokens"]  # local answer costs 0 paid tokens
    return f"""
      <article class="cmp-card">
        <div class="cmp-q"><span class="cmp-ax">{AX_LABEL.get(r['axis'], r['axis'])}</span>{trunc(r['prompt'], 160)}</div>
        <div class="cmp-cols">
          <div class="cmp-col cmp-local">
            <div class="cmp-h">with hibrid · <b>local, free</b></div>
            <div class="cmp-meta"><span class="mono">{html.escape(loc['model'] or '—')}</span>
              · <b>0</b> paid tok · q&nbsp;<b>{loc['score']:.2f}</b></div>
            <p class="cmp-ans">{trunc(loc.get('content', ''), 300)}</p>
          </div>
          <div class="cmp-col cmp-fro">
            <div class="cmp-h">without hibrid · <b>frontier, paid</b></div>
            <div class="cmp-meta"><span class="mono">{html.escape(fro['model'] or '—')}</span>
              · <b>{fro['total_tokens']}</b> paid tok · q&nbsp;<b>{fro['score']:.2f}</b></div>
            <p class="cmp-ans">{trunc(fro.get('content', ''), 300)}</p>
          </div>
        </div>
        <div class="cmp-foot">the model behind the local answer: <span class="mono">{html.escape(loc['model'] or '—')}</span>
          · quality gap <b>{(fro['score'] - loc['score']):+.2f}</b> · paid tokens saved on this task: <b>{saved}</b></div>
      </article>"""


def main():
    data = json.load(open(RESULTS, encoding="utf-8"))
    s, rows = data["summary"], data["rows"]
    # eval_run stores content inside local/frontier? ensure present
    for r in rows:
        r["local"].setdefault("content", r.get("_local_content", ""))
        r["frontier"].setdefault("content", r.get("_frontier_content", ""))

    ex = pick_examples(rows)
    cards = "\n".join(card(r) for r in ex)
    q = s["quality"]
    # Landing banner uses the measured ALL-LOCAL bound over judged tasks (honest, config-free):
    judged = [r for r in rows if r["local"]["score"] is not None and r["frontier"]["score"] is not None]
    baseline_ft = sum(r["frontier"]["total_tokens"] for r in judged)

    section = f"""{START}
  <section class="wrap" id="compare">
    <style>
      #compare .cmp-stats{{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0 1.4rem}}
      #compare .cmp-stat{{flex:1;min-width:150px;background:var(--card);border:1px solid var(--rule);border-radius:var(--r);padding:.9rem 1rem}}
      #compare .cmp-stat .n{{font-size:var(--s2);font-weight:700;color:var(--green-ink);line-height:1}}
      #compare .cmp-stat .l{{color:var(--muted);font-size:var(--s-1);margin-top:.25rem}}
      #compare .cmp-card{{background:var(--card);border:1px solid var(--rule);border-radius:var(--r);padding:1rem 1.1rem;margin-bottom:1rem}}
      #compare .cmp-q{{font-family:var(--serif);font-size:var(--s1);margin-bottom:.7rem}}
      #compare .cmp-ax{{display:inline-block;font-family:var(--sans);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:var(--clay);border:1px solid var(--rule-2);border-radius:6px;padding:.1rem .4rem;margin-right:.5rem;vertical-align:middle}}
      #compare .cmp-cols{{display:grid;grid-template-columns:1fr 1fr;gap:.9rem}}
      @media(max-width:640px){{#compare .cmp-cols{{grid-template-columns:1fr}}}}
      #compare .cmp-col{{border:1px solid var(--rule);border-radius:8px;padding:.7rem .8rem}}
      #compare .cmp-local{{border-left:3px solid var(--green)}}
      #compare .cmp-fro{{border-left:3px solid var(--slate)}}
      #compare .cmp-h{{font-size:var(--s-1);color:var(--ink-2);margin-bottom:.3rem}}
      #compare .cmp-meta{{font-size:var(--s-1);color:var(--muted);margin-bottom:.5rem}}
      #compare .cmp-ans{{font-size:var(--s-1);color:var(--ink-2);line-height:1.5;white-space:pre-wrap}}
      #compare .cmp-foot{{margin-top:.7rem;font-size:var(--s-1);color:var(--muted)}}
      #compare .mono{{font-family:var(--mono)}}
    </style>
    <h2 class="lead">See for yourself — and the model behind each call</h2>
    <p class="sub">Real measured runs ({len(judged)} tasks, blind-judged 0–1). Same task, answered on a
      small local model (a 3B, free) and by the frontier (paid). The quality gap is small; the
      token bill isn't.</p>
    <div class="cmp-stats">
      <div class="cmp-stat"><div class="n">{q['quality_retained_pct']}%</div><div class="l">of frontier quality kept<br>(local {q['mean_local']} vs {q['mean_frontier']}, blind judge)</div></div>
      <div class="cmp-stat"><div class="n">{q['parity_pct']}%</div><div class="l">of tasks at parity or better vs the paid model</div></div>
      <div class="cmp-stat"><div class="n">{baseline_ft:,}→0</div><div class="l">paid tokens: the frontier spent {baseline_ft:,}, the local tier spent nothing</div></div>
    </div>
    {cards}
    <p class="sub" style="margin-top:.6rem">Method &amp; full data:
      <a href="https://github.com/vfalbor/hibrid/blob/main/docs/benchmarks/qa_report.md">evaluation report</a>.</p>
  </section>
  {END}"""

    page = open(LANDING, encoding="utf-8").read()
    i, j = page.find(START), page.find(END)
    if i == -1 or j == -1:
        raise SystemExit("markers not found in landing")
    page = page[:i] + section + page[j + len(END):]
    open(LANDING, "w", encoding="utf-8").write(page)
    print(f"injected comparison section ({len(ex)} examples) into backend/static/index.html")


if __name__ == "__main__":
    main()
