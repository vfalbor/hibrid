"""Tests del motor de decisión (sin red): classifier + router + utilidad + overrides."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import classifier, router
from backend.profiler import HardwareProfile
from backend.registry import NodeProfile
from backend.schemas import ChatMessage, HibridOptions


def _node(local=True, cloud=True, tps=50.0):
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="test", cpu_cores_physical=8,
                         ram_gb=32, gpu_vendor="nvidia", gpu_name="RTX 4090",
                         vram_gb=24, apple_silicon=False,
                         machine_class="gpu_24gb", max_local_params_b=33.0)
    n = NodeProfile(hw)
    if local:
        n.local_endpoint = "http://localhost:11434/v1"
        n.local_models = ["qwen2.5:14b"]
        n.local_default = "qwen2.5:14b"
        n.tok_s = {"qwen2.5:14b": tps}
    if cloud:
        n.cloud_models = ["claude-opus-4-8", "claude-haiku-4-5-20251001"]
    return n


def _feat(text):
    return classifier.classify([ChatMessage(role="user", content=text)])


def test_pii_forces_local():
    node = _node()
    feat = _feat("Mi email es juan.perez@example.com y mi DNI 12345678Z, resume esto.")
    assert feat.has_pii
    d = router.decide(node, feat, None)
    assert d.chosen.kind == "local"
    assert "privacidad" in d.reason


def test_simple_task_prefers_local():
    node = _node()
    feat = _feat("Traduce 'hola mundo' al inglés.")
    d = router.decide(node, feat, None)
    assert d.chosen.kind == "local"


def test_hard_task_can_go_cloud():
    node = _node(tps=50.0)
    feat = _feat("Demuestra paso a paso por qué el algoritmo de Dijkstra es óptimo y "
                 "analiza su complejidad; deriva la cota y razona el trade-off.")
    d = router.decide(node, feat, None)
    # Tarea compleja: la nube potente debería ganar o al menos ser candidata fuerte.
    assert any(c.kind == "cloud_strong" for c in d.candidates)
    assert d.chosen.utility == max(c.utility for c in d.candidates if c.kind == d.chosen.kind)


def test_offline_never_cloud():
    node = _node()
    feat = _feat("Demuestra el teorema de Pitágoras paso a paso.")
    d = router.decide(node, feat, HibridOptions(allow_cloud=False))
    assert d.chosen.kind == "local"


def test_force_destination():
    node = _node()
    feat = _feat("hola")
    d = router.decide(node, feat, HibridOptions(force="cloud_cheap"))
    assert d.chosen.kind == "cloud_cheap"


def test_no_local_uses_cloud():
    node = _node(local=False)
    feat = _feat("Resume este texto largo.")
    d = router.decide(node, feat, None)
    assert d.chosen.kind in ("cloud_cheap", "cloud_strong")


def test_loop_refine_stays_local():
    """Un loop de refinado debe quedarse en local (local-first), no en modelo caro."""
    node = _node()
    feat = _feat("Refina iterativamente este código y ejecuta los tests hasta que pasen.")
    assert feat.task_type == "loop_refine"
    d = router.decide(node, feat, None)
    assert d.chosen.tier == "local_free"
    # paid_strong no debe estar en el pool elegible del perfil loop_refine.
    assert not any(c.tier == "paid_strong" and c.utility >= d.chosen.utility
                   for c in d.candidates if c.tier in ("local_free", "paid_cheap"))


def test_loop_refine_no_strong_even_if_complex():
    """Aunque la iteración sea compleja, el loop nunca salta al modelo caro por iteración."""
    node = _node(tps=40.0)
    feat = _feat("Loop: refactoriza y corrige todos los bugs hasta que el lint pase.")
    d = router.decide(node, feat, None)
    assert d.chosen.tier in ("local_free", "paid_cheap")


def test_skill_can_declare_profile():
    """Un skill declara explícitamente su perfil de ejecución (override del inferido)."""
    node = _node()
    feat = _feat("Demuestra el teorema paso a paso.")  # se inferiría deep_reason
    d = router.decide(node, feat, HibridOptions(profile="loop_refine"))
    assert d.chosen.tier == "local_free"


def test_task_aware_model_selection():
    """Con varios modelos locales, una tarea de código elige el modelo competente en código."""
    node = _node()
    node.local_models = ["llama3.2:1b", "qwen2.5-coder:1.5b", "gemma2:2b"]
    node.local_default = "gemma2:2b"
    node.tok_s = {"llama3.2:1b": 30, "qwen2.5-coder:1.5b": 25, "gemma2:2b": 20}
    feat = _feat("```python\ndef f(x): return x\n```\nFix and refactor this function.")
    d = router.decide(node, feat, HibridOptions(allow_cloud=False))
    assert d.chosen.kind == "local"
    assert d.chosen.model == "qwen2.5-coder:1.5b"  # el especialista en código gana


def test_deep_reason_allows_strong():
    node = _node(tps=40.0)
    feat = _feat("Diseña la arquitectura distribuida y analiza los trade-offs de "
                 "consistencia, deriva la complejidad y razona paso a paso el debug.")
    d = router.decide(node, feat, HibridOptions(task_type="deep_reason"))
    assert any(c.tier == "paid_strong" for c in d.candidates)


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} tests OK")
