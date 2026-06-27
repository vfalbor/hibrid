"""Tests de la capa de orquestación: task_policy, catálogo orquestado, descubrimiento
y selección adaptativa de backends. Sin red."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import backends as B
from backend import classifier, models_catalog as MC, router, task_policy as TP
from backend.backends import Backend
from backend.profiler import HardwareProfile
from backend.registry import NodeProfile
from backend.schemas import ChatMessage, HibridOptions


# ----------------------- task_policy (matriz explícita) -----------------------

def test_policy_axes():
    assert TP.policy_for("loop_refine").axis == "code"
    assert TP.policy_for("deep_reason").axis == "reasoning"
    assert TP.policy_for("simple").axis == "general"
    assert TP.policy_for("nope").task_type == "general"  # fallback


def test_axis_for_code_overrides():
    assert TP.axis_for("simple", has_code=True) == "code"
    assert TP.axis_for("deep_reason", has_code=False) == "reasoning"
    assert TP.axis_for("loop_verify", has_code=False) == "code"


def test_policy_table_renders():
    rows = TP.as_table()
    assert any(r["task_type"] == "loop_refine" and r["paid_cap"] == "paid_cheap" for r in rows)


# ----------------------- catálogo orquestado por eje -----------------------

def test_orchestrated_axis_and_tier():
    assert MC.orchestrated_tier("claude-opus-4-8") == "paid_strong"
    assert MC.orchestrated_tier("claude-haiku-4-5-20251001") == "paid_cheap"
    assert MC.orchestrated_capability("claude-opus-4-8", "reasoning") > \
           MC.orchestrated_capability("claude-haiku-4-5-20251001", "reasoning")


def test_best_orchestrated_picks_cheaper_at_parity():
    # Dentro de paid_strong, para 'code', opus gana en competencia.
    avail = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    assert MC.best_orchestrated_for("code", avail, "paid_strong") == "claude-opus-4-8"
    # En paid_cheap sólo está haiku.
    assert MC.best_orchestrated_for("code", avail, "paid_cheap") == "claude-haiku-4-5-20251001"


# ----------------------- descubrimiento de backends -----------------------

def test_discover_handles_no_agents(monkeypatch):
    monkeypatch.setattr(B.shutil, "which", lambda b: None)  # ningún CLI instalado
    monkeypatch.delenv("HIBRID_SKILLS_URL", raising=False)
    monkeypatch.delenv("HIBRID_HARNESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    bks = B.discover_backends()
    assert all(not b.available for b in bks)            # CLIs presentes pero no disponibles
    assert B.available_orchestrated_models(bks) == []   # sin tier de pago alcanzable


def test_discover_finds_logged_in_cli(monkeypatch):
    monkeypatch.setattr(B.shutil, "which", lambda b: f"/usr/bin/{b}" if b == "claude" else None)
    monkeypatch.delenv("HIBRID_SKILLS_URL", raising=False)
    bks = B.discover_backends()
    claude = next(b for b in bks if b.id == "cli:claude")
    assert claude.available
    assert "claude-opus-4-8" in B.available_orchestrated_models(bks)


def test_discover_service_and_passthrough(monkeypatch):
    monkeypatch.setattr(B.shutil, "which", lambda b: None)
    monkeypatch.setenv("HIBRID_SKILLS_URL", "http://localhost:9000")
    monkeypatch.setenv("HIBRID_HARNESS_TOKEN", "tok")
    bks = B.discover_backends()
    assert any(b.id == "service" and b.available for b in bks)
    assert any(b.id == "passthrough" and b.available for b in bks)


# ----------------------- selección adaptativa -----------------------

def test_pick_backend_lowest_latency():
    slow = Backend("cli:codex", "cli", "codex", ["gpt-4o"], True, latency_s=4.0)
    fast = Backend("service", "service", "", ["gpt-4o"], True, latency_s=1.0)
    down = Backend("cli:opencode", "cli", "opencode", ["gpt-4o"], False, latency_s=0.5)
    assert B.pick_backend([slow, fast, down], "gpt-4o").id == "service"
    # Si el rápido cae, cae al siguiente disponible (adaptativo).
    fast.available = False
    assert B.pick_backend([slow, fast, down], "gpt-4o").id == "cli:codex"


def _node_with(backends, models):
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="t", cpu_cores_physical=8, ram_gb=32,
                         gpu_vendor="nvidia", gpu_name="x", vram_gb=24, apple_silicon=False,
                         machine_class="gpu_24gb", max_local_params_b=33.0)
    n = NodeProfile(hw)
    n.local_endpoint = "http://localhost:11434/v1"
    n.local_models = ["qwen2.5:14b"]; n.local_default = "qwen2.5:14b"; n.tok_s = {"qwen2.5:14b": 40}
    n.cloud_models = models
    n.backends = backends
    return n


def test_router_no_paid_candidate_without_backend():
    """Si hay modelos de pago listados pero NINGÚN backend los sirve, no hay candidato de pago."""
    node = _node_with([], ["claude-opus-4-8"])  # sin backends
    feat = classifier.classify([ChatMessage(role="user",
            content="Diseña la arquitectura y razona los trade-offs paso a paso.")])
    d = router.decide(node, feat, HibridOptions(task_type="deep_reason"))
    assert all(c.kind == "local" for c in d.candidates)


def test_router_binds_backend_to_paid_destination():
    bk = Backend("cli:claude", "cli", "claude", ["claude-opus-4-8", "claude-haiku-4-5-20251001"],
                 True, latency_s=2.0)
    node = _node_with([bk], ["claude-opus-4-8", "claude-haiku-4-5-20251001"])
    feat = classifier.classify([ChatMessage(role="user",
            content="Diseña la arquitectura distribuida, deriva la complejidad y razona el debug.")])
    d = router.decide(node, feat, HibridOptions(task_type="deep_reason"))
    strong = next(c for c in d.candidates if c.tier == "paid_strong")
    assert strong.backend == "cli:claude"
    assert strong.model == "claude-opus-4-8"


if __name__ == "__main__":
    import traceback
    # ejecución directa sin pytest: stubs mínimos de monkeypatch no soportados aquí.
    print("run via: python -m pytest tests/test_backends.py")
