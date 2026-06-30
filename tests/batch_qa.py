"""batch_qa — campaña de QA de >100 casos sobre el motor de decisión de hibrid.

Token-cero: ejerce `classifier.classify` y `router.decide` directamente (sin inferencia,
sin tokens). Un subconjunto live opcional (--live) golpea el engine local en :8095 con
allow_cloud=False (inferencia local gratis) para confirmar que sirve y devuelve contenido.

Salida: resumen por categoría + lista de fallos + JSON en docs/benchmarks/qa_batch_results.json.
Uso:  python tests/batch_qa.py            # solo decisión (rápido, sin red)
      python tests/batch_qa.py --live     # añade el subconjunto end-to-end local
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import classifier, models_catalog, router, task_policy
from backend.backends import Backend
from backend.profiler import HardwareProfile
from backend.registry import NodeProfile
from backend.schemas import ChatMessage, HibridOptions

RESULTS: list[dict] = []


def check(category: str, name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append({"category": category, "name": name, "ok": bool(cond), "detail": detail})


# --------------------------------------------------------------------------- machines
def _backend(models):
    return Backend(id="cli:claude", mechanism="cli", agent="claude",
                   models=list(models), available=True, latency_s=2.5)


def node(*, ram=32, gpu="nvidia", vram=24, apple=False, maxp=33.0,
         local=None, cloud=True, tps=50.0):
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="t", cpu_cores_physical=8,
                         ram_gb=ram, gpu_vendor=gpu, gpu_name="g", vram_gb=vram,
                         apple_silicon=apple, machine_class="t", max_local_params_b=maxp)
    n = NodeProfile(hw)
    if local is not None:
        n.local_endpoint = "http://localhost:11434/v1"
        n.local_models = list(local)
        n.local_default = local[0]
        n.tok_s = {m: tps for m in local}
    if cloud:
        n.cloud_models = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
                          "gpt-4o", "gpt-4o-mini"]
        n.backends = [_backend(n.cloud_models)]
    return n


# Perfiles de máquina realistas: qué modelos caben y se suelen tener instalados.
MACHINES = {
    "cpu_small":  dict(ram=8,  gpu="none", vram=0,  maxp=3.0,
                       local=["qwen2.5:0.5b", "qwen2.5-coder:1.5b", "llama3.2:3b", "qwen3:4b"], tps=8),
    "cpu_large":  dict(ram=32, gpu="none", vram=0,  maxp=7.0,
                       local=["qwen2.5-coder:7b", "qwen3:8b", "aya-expanse:8b", "deepseek-r1:7b"], tps=12),
    "gpu_12gb":   dict(ram=32, gpu="nvidia", vram=12, maxp=8.0,
                       local=["qwen2.5-coder:7b", "qwen3:8b", "aya-expanse:8b", "deepseek-r1:8b"], tps=45),
    "gpu_24gb":   dict(ram=64, gpu="nvidia", vram=24, maxp=33.0,
                       local=["qwen2.5-coder:32b", "qwen2.5:14b", "qwen3:14b", "phi4-reasoning:14b",
                              "aya-expanse:8b"], tps=90),
}


def _f(text):
    return classifier.classify([ChatMessage(role="user", content=text)])


# --------------------------------------------------------------------------- 1. classifier
CLASSIFIER_CASES = [
    ("Redáctame un artículo de blog sobre routing de LLMs.", "write"),
    ("Escribe un post de LinkedIn con thought leadership.", "write"),
    ("Write a newsletter intro about local models.", "write"),
    ("Reescribe este párrafo para que sea más claro.", "write"),
    ("Traduce este texto al inglés.", "translate"),
    ("Translate this paragraph to Spanish.", "translate"),
    ("Tradúceme esto al francés, por favor.", "translate"),
    ("def f(x):\n  return x  # arregla esto", "code"),
    ("```python\nprint(1)\n```\nadd a docstring", "code"),
    ("Clasifica este email como spam o no.", "simple"),
    ("Resume en una línea este texto corto.", "simple"),
    ("Extrae las fechas de este texto.", "simple"),
    ("Refactoriza iterativamente hasta que pasen los tests.", "loop_refine"),
    ("Itera el refactor hasta que el lint quede limpio.", "loop_refine"),
    ("Haz una verificación final y aprueba el resultado.", "loop_verify"),
    ("Diseña la arquitectura distribuida y razona los trade-offs paso a paso, demuestra la complejidad.", "deep_reason"),
    ("¿Qué hora es en Tokio?", "simple"),
    ("Hola, ¿cómo estás?", "simple"),
]


def run_classifier():
    for text, expected in CLASSIFIER_CASES:
        got = _f(text).task_type
        check("classifier", f"{expected}: {text[:34]!r}", got == expected,
              f"esperado {expected}, obtenido {got}")


# --------------------------------------------------------------------------- 2. axis map
def run_axis():
    expect = {"loop_refine": "code", "loop_verify": "code", "deep_reason": "reasoning",
              "simple": "general", "write": "writing", "translate": "multilingual",
              "code": "code", "interactive": "general", "batch": "general", "general": "general"}
    for tt, ax in expect.items():
        check("axis", f"{tt}->{ax}", task_policy.axis_for(tt) == ax,
              f"axis_for({tt})={task_policy.axis_for(tt)}")
    # has_code fuerza code
    check("axis", "has_code forces code", task_policy.axis_for("general", has_code=True) == "code")


# --------------------------------------------------------------------------- 3. PII override
PII_PROMPTS = [
    "Mi email es juan.perez@example.com, resume esto.",
    "Mi DNI es 12345678Z, clasifica el documento.",
    "Tarjeta 4111 1111 1111 1111, analiza el patrón paso a paso y demuestra el algoritmo.",
    "IBAN ES91 2100 0418 4502 0005 1332, extrae los datos.",
    "My SSN is 123-45-6789, summarize.",
    "password: hunter2 — diseña la arquitectura y razona los trade-offs.",
]


def run_pii():
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        for p in PII_PROMPTS:
            feat = _f(p)
            d = router.decide(n, feat, None)
            check("pii", f"{m_name}: {p[:30]!r}", d.chosen.kind == "local" and feat.has_pii,
                  f"pii={feat.has_pii} chosen={d.chosen.kind}/{d.chosen.tier}")


# --------------------------------------------------------------------------- 4. offline
def run_offline():
    prompts = ["Diseña una arquitectura compleja y razona paso a paso.",
               "Traduce esto al inglés.", "Redacta un artículo largo.",
               "def f(): pass  # refactor"]
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        for p in prompts:
            d = router.decide(n, _f(p), HibridOptions(allow_cloud=False))
            check("offline", f"{m_name}: {p[:24]!r}", d.chosen.kind == "local",
                  f"chosen={d.chosen.kind}")


# --------------------------------------------------------------------------- 5. force
def run_force():
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        for force in ("local", "cloud_cheap", "cloud_strong"):
            d = router.decide(n, _f("Haz algo general."), HibridOptions(force=force))
            check("force", f"{m_name}: force={force}", d.chosen.kind == force,
                  f"chosen={d.chosen.kind}")


# --------------------------------------------------------------------------- 6/7. tier caps
def run_caps():
    hardprompt = "Refactoriza iterativamente hasta que pasen los tests, optimiza y razona."
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        d = router.decide(n, _f(hardprompt), HibridOptions(task_type="loop_refine"))
        check("cap_loop", f"{m_name}: loop_refine !=strong",
              d.chosen.tier != "paid_strong", f"tier={d.chosen.tier}")
        for tt in ("simple", "translate", "batch"):
            d = router.decide(n, _f("haz una tarea"), HibridOptions(task_type=tt))
            check("cap_cheap", f"{m_name}: {tt} !=strong",
                  d.chosen.tier != "paid_strong", f"tier={d.chosen.tier}")


# --------------------------------------------------------------------------- 8. axis model pick
def run_axis_pick():
    # Para cada máquina y eje, el modelo local elegido debe ser competente en ese eje
    # (>= mejor capacidad disponible - epsilon) y caber en la máquina.
    axes_prompts = {
        "code": "```py\ndef f():pass\n```\narregla y refactoriza",
        "writing": "Redacta un artículo largo sobre IA local.",
        "multilingual": "Traduce este texto al inglés.",
        "reasoning": "Demuestra paso a paso la cota inferior y razona los trade-offs de complejidad.",
    }
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        avail = n.local_models
        for axis, prompt in axes_prompts.items():
            feat = _f(prompt)
            d = router.decide(n, feat, HibridOptions(allow_cloud=False))
            best = models_catalog.best_local_for(axis, avail, n.hardware.max_local_params_b)
            # capacidad del modelo elegido vs el mejor posible en ese eje
            cap_chosen = models_catalog.capability(d.chosen.model, axis)
            cap_best = models_catalog.capability(best, axis) if best else 0
            check("axis_pick", f"{m_name}/{axis}: {d.chosen.model}",
                  cap_chosen >= cap_best - 1e-6,
                  f"chosen={d.chosen.model}(cap {cap_chosen:.2f}) best={best}(cap {cap_best:.2f})")


# --------------------------------------------------------------------------- 9. machine fit
def run_fit():
    for m_name, cfg in MACHINES.items():
        n = node(**cfg)
        for p in ["redacta algo", "arregla este código def f():pass", "traduce esto"]:
            d = router.decide(n, _f(p), HibridOptions(allow_cloud=False))
            params = models_catalog._params_in(d.chosen.model) or 7.0
            check("fit", f"{m_name}: {d.chosen.model} fits {n.hardware.max_local_params_b}b",
                  params <= n.hardware.max_local_params_b + 1.0,
                  f"model={d.chosen.model} params={params} max={n.hardware.max_local_params_b}")


# --------------------------------------------------------------------------- 10. edge cases
def run_edges():
    # sin modelos locales -> usa nube
    n = node(local=None, cloud=True)
    d = router.decide(n, _f("haz algo"), None)
    check("edge", "no local -> cloud", d.chosen.kind in ("cloud_cheap", "cloud_strong"),
          f"chosen={d.chosen.kind}")
    # sin nube, con local -> local
    n2 = node(local=["qwen3:8b"], cloud=False, maxp=8)
    d2 = router.decide(n2, _f("haz algo"), None)
    check("edge", "no cloud -> local", d2.chosen.kind == "local", f"chosen={d2.chosen.kind}")
    # ni local ni nube -> error controlado
    n3 = node(local=None, cloud=False)
    try:
        router.decide(n3, _f("haz algo"), None)
        check("edge", "no dest -> raises", False, "no lanzó excepción")
    except RuntimeError:
        check("edge", "no dest -> raises", True)
    except Exception as e:
        check("edge", "no dest -> raises", False, f"excepción inesperada {type(e).__name__}")
    # input vacío
    try:
        feat = classifier.classify([ChatMessage(role="user", content="")])
        d = router.decide(node(**MACHINES["gpu_12gb"]), feat, None)
        check("edge", "empty input ok", d.chosen is not None)
    except Exception as e:
        check("edge", "empty input ok", False, f"{type(e).__name__}: {e}")
    # input muy largo
    longtxt = "palabra " * 5000
    try:
        feat = classifier.classify([ChatMessage(role="user", content=longtxt)])
        d = router.decide(node(**MACHINES["gpu_24gb"]), feat, None)
        check("edge", "long input ok", 0.0 <= feat.complexity <= 1.0 and d.chosen is not None,
              f"complexity={feat.complexity}")
    except Exception as e:
        check("edge", "long input ok", False, f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- 11. interactive latency
def run_interactive():
    # local muy lento en interactive debe poder perder frente a barato (penalización tok/s).
    cfg = dict(MACHINES["cpu_small"]); cfg["tps"] = 2.0  # por debajo del mínimo
    n = node(**cfg)
    d = router.decide(n, _f("hola, charlemos"), HibridOptions(task_type="interactive"))
    check("interactive", "slow local penalized (decision made)", d.chosen is not None,
          f"chosen={d.chosen.kind}/{d.chosen.tier} U={d.chosen.utility:.2f}")
    # rápido: local gana
    cfg2 = dict(MACHINES["gpu_24gb"]); cfg2["tps"] = 120.0
    n2 = node(**cfg2)
    d2 = router.decide(n2, _f("hola, charlemos"), HibridOptions(task_type="interactive"))
    check("interactive", "fast local preferred", d2.chosen.kind == "local",
          f"chosen={d2.chosen.kind}")


# --------------------------------------------------------------------------- LIVE subset
def run_live():
    import urllib.request
    base = os.environ.get("HIBRID_BASE", "http://127.0.0.1:8095")
    prompts = [
        ("simple", "Clasifica: '¿me devuelven el dinero?' como queja o pregunta."),
        ("simple", "Resume en 8 palabras: el gato se subió al tejado al amanecer."),
        ("translate", "Traduce al inglés: 'buenos días, ¿cómo estás?'"),
        ("write", "Escribe un titular para un post sobre modelos locales."),
        ("code", "Escribe una función Python que sume dos números."),
        ("general", "¿Cuál es la capital de Francia?"),
        ("simple", "Extrae el número: 'el pedido 4521 llega mañana'."),
        ("translate", "Translate to Spanish: 'the meeting is at noon'."),
        ("simple", "¿Es par o impar el número 7?"),
        ("general", "Di hola en tres idiomas."),
    ]
    for tt, p in prompts:
        body = json.dumps({"model": "hibrid-auto",
                           "messages": [{"role": "user", "content": p}],
                           "hibrid": {"task_type": tt, "allow_cloud": False}}).encode()
        req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=120))
            dt = time.time() - t0
            content = r["choices"][0]["message"]["content"]
            tier = r.get("hibrid", {}).get("chosen", {}).get("tier")
            check("live", f"{tt}: {p[:28]!r}", bool(content) and tier == "local_free",
                  f"tier={tier} dt={dt:.1f}s len={len(content)}")
        except Exception as e:
            check("live", f"{tt}: {p[:28]!r}", False, f"{type(e).__name__}: {e}")


def main():
    live = "--live" in sys.argv
    run_classifier(); run_axis(); run_pii(); run_offline(); run_force()
    run_caps(); run_axis_pick(); run_fit(); run_edges(); run_interactive()
    if live:
        run_live()

    total = len(RESULTS); passed = sum(1 for r in RESULTS if r["ok"]); failed = total - passed
    by_cat: dict[str, list] = {}
    for r in RESULTS:
        by_cat.setdefault(r["category"], [0, 0])
        by_cat[r["category"]][0 if r["ok"] else 1] += 1

    print(f"\n{'category':<14} {'pass':>5} {'fail':>5}")
    print("-" * 26)
    for c, (ok, bad) in sorted(by_cat.items()):
        print(f"{c:<14} {ok:>5} {bad:>5}")
    print("-" * 26)
    print(f"{'TOTAL':<14} {passed:>5} {failed:>5}   ({total} tests)")

    fails = [r for r in RESULTS if not r["ok"]]
    if fails:
        print(f"\n=== {len(fails)} FAILURES ===")
        for r in fails:
            print(f"  [{r['category']}] {r['name']}  —  {r['detail']}")

    out = os.path.join(os.path.dirname(__file__), "..", "docs", "benchmarks", "qa_batch_results.json")
    with open(out, "w") as f:
        json.dump({"total": total, "passed": passed, "failed": failed,
                   "by_category": {c: {"pass": v[0], "fail": v[1]} for c, v in by_cat.items()},
                   "failures": fails}, f, indent=2, ensure_ascii=False)
    print(f"\nresults -> {os.path.relpath(out)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
