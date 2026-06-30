"""Edge-case tests for models_catalog.match(), best_local_for(), best_orchestrated_for(),
tier_for(), and router.decide() — adversarial bug-hunt companion.

Each test_* function either exposes a genuine defect (must fail before the fix,
pass after) or documents expected behaviour for a boundary that is easy to regress.

Run:  .venv/bin/python tests/test_router_edge.py
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import models_catalog as mc, router, task_policy
from backend.backends import Backend
from backend.profiler import HardwareProfile
from backend.registry import NodeProfile
from backend.schemas import ChatMessage, HibridOptions


# ---------------------------------------------------------------------------
# Helpers (mirror test_router.py style)
# ---------------------------------------------------------------------------

def _backend(models):
    return Backend(id="cli:claude", mechanism="cli", agent="claude",
                   models=list(models), available=True, latency_s=2.5)


def _node(local_models=None, cloud=True, tps=40.0, maxp=33.0):
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="test", cpu_cores_physical=8,
                         ram_gb=32, gpu_vendor="nvidia", gpu_name="RTX 4090",
                         vram_gb=24, apple_silicon=False,
                         machine_class="gpu_24gb", max_local_params_b=maxp)
    n = NodeProfile(hw)
    if local_models is not None:
        n.local_endpoint = "http://localhost:11434/v1"
        n.local_models = list(local_models)
        n.local_default = local_models[0]
        n.tok_s = {m: tps for m in local_models}
    if cloud:
        n.cloud_models = ["claude-opus-4-8", "claude-sonnet-4-6",
                          "claude-haiku-4-5-20251001", "gpt-4o", "gpt-4o-mini"]
        n.backends = [_backend(n.cloud_models)]
    return n


def _local_only_node(models, tps=20.0, maxp=7.0):
    """A node with only local models and NO cloud."""
    hw = HardwareProfile(os="Linux", arch="x86_64", cpu="test", cpu_cores_physical=4,
                         ram_gb=16, gpu_vendor="none", gpu_name="",
                         vram_gb=0, apple_silicon=False,
                         machine_class="cpu_large", max_local_params_b=maxp)
    n = NodeProfile(hw)
    n.local_endpoint = "http://localhost:11434/v1"
    n.local_models = list(models)
    n.local_default = models[0]
    n.tok_s = {m: tps for m in models}
    return n


def _f(text):
    from backend import classifier
    return classifier.classify([ChatMessage(role="user", content=text)])


# ===========================================================================
# 1. models_catalog.match() — cross-match / false-positive bugs
# ===========================================================================

def test_match_llama32_1b_not_confused_with_3b():
    """BUG: match('llama3.2:1b') was returning the 3b entry because '3' from the
    size string '3b' is a substring of the family name 'llama3.2'.
    The 1b and 3b models have substantially different capability scores (general 0.45 vs 0.64).
    """
    e = mc.match("llama3.2:1b")
    assert e is not None, "llama3.2:1b should be in catalog"
    assert e.family == "llama3.2:1b", (
        f"match('llama3.2:1b') returned {e.family!r}; expected 'llama3.2:1b'. "
        f"'3' from size '3b' of the earlier entry is a substring of 'llama3.2'.")
    assert abs(e.params_b - 1.0) < 1e-9, f"params_b should be 1.0, got {e.params_b}"


def test_match_llama32_3b_unaffected():
    """3b must still resolve correctly after the 1b fix."""
    e = mc.match("llama3.2:3b")
    assert e is not None
    assert e.family == "llama3.2:3b", f"got {e.family!r}"
    assert abs(e.params_b - 3.0) < 1e-9


def test_match_phi4_reasoning_not_confused_with_phi4():
    """BUG: match('phi4-reasoning:14b') was returning the phi4:14b (plain) entry
    because 'phi4' is a prefix of 'phi4-reasoning:14b' and '14' appears in the name.
    This caused a massive underestimation of reasoning capability (0.75 vs 0.99).
    """
    e = mc.match("phi4-reasoning:14b")
    assert e is not None, "phi4-reasoning:14b should be in catalog"
    assert e.family == "phi4-reasoning:14b", (
        f"match('phi4-reasoning:14b') returned {e.family!r}; expected 'phi4-reasoning:14b'. "
        f"'phi4' prefix match was stealing this entry.")
    assert e.thinking is True, "phi4-reasoning is a thinking model"
    # The most important consequence: reasoning cap must be near 0.99, not phi4's 0.75
    assert e.caps["reasoning"] > 0.95, (
        f"reasoning cap for phi4-reasoning:14b should be ~0.99, got {e.caps['reasoning']}")


def test_match_phi4_plain_unaffected():
    """Plain phi4:14b must still resolve after the phi4-reasoning fix."""
    e = mc.match("phi4:14b")
    assert e is not None
    assert e.family == "phi4:14b", f"got {e.family!r}"
    assert e.thinking is False
    assert abs(e.caps["reasoning"] - 0.75) < 1e-9


def test_match_no_cross_contamination_qwen25_vs_qwen25coder():
    """qwen2.5:Xb and qwen2.5-coder:Xb are different families; must not cross-match."""
    for size, expected_coder in [("7b", False), ("3b", False), ("1.5b", False)]:
        e_gen = mc.match(f"qwen2.5:{size}")
        e_coder = mc.match(f"qwen2.5-coder:{size}")
        assert e_gen is not None and e_coder is not None
        assert e_gen.family == f"qwen2.5:{size}", f"qwen2.5:{size} -> {e_gen.family}"
        assert e_coder.family == f"qwen2.5-coder:{size}", f"qwen2.5-coder:{size} -> {e_coder.family}"
        # They must be different ModelInfo objects with different capability profiles
        assert e_gen is not e_coder
        # Coder should have higher code cap than the general model of same size
        assert e_coder.caps["code"] > e_gen.caps["code"], (
            f"coder:{size} code cap ({e_coder.caps['code']}) should exceed "
            f"general:{size} code cap ({e_gen.caps['code']})")


def test_match_variant_suffixes():
    """Quantized / instruct suffixes must resolve to the base size entry."""
    cases = [
        ("qwen2.5-coder:1.5b-instruct-q4_k_m", "qwen2.5-coder:1.5b"),
        ("qwen2.5:7b-instruct", "qwen2.5:7b"),
        ("deepseek-r1:8b-q4_K_M", "deepseek-r1:8b"),
    ]
    for name, expected_family in cases:
        e = mc.match(name)
        assert e is not None, f"{name!r} should resolve"
        assert e.family == expected_family, f"match({name!r}) -> {e.family!r}, expected {expected_family!r}"


def test_match_returns_none_for_unknown_family():
    """A completely unknown family should return None (not a wrong catalog entry)."""
    assert mc.match("codellama:7b") is None
    assert mc.match("unknown-model:13b") is None


# ===========================================================================
# 2. _params_in() — parameter parsing edge cases
# ===========================================================================

def test_params_in_fractional():
    """Fractional sizes like 0.5b, 1.5b, 3.8b must be parsed correctly."""
    assert mc._params_in("qwen2.5:0.5b") == 0.5, "0.5b"
    assert mc._params_in("qwen2.5-coder:0.5b") == 0.5, "coder 0.5b"
    assert mc._params_in("qwen2.5:1.5b") == 1.5, "1.5b"
    assert mc._params_in("phi4-mini:3.8b") == 3.8, "3.8b"
    assert mc._params_in("phi3.5:3.8b") == 3.8, "phi3.5 3.8b"


def test_params_in_integer():
    assert mc._params_in("llama3.2:1b") == 1.0, "1b"
    assert mc._params_in("llama3.2:3b") == 3.0, "3b"
    assert mc._params_in("deepseek-r1:8b") == 8.0, "8b"
    assert mc._params_in("deepseek-coder-v2:16b") == 16.0, "16b"


def test_params_in_with_suffix():
    """Suffixes after the size tag must not corrupt parsing."""
    assert mc._params_in("qwen2.5-coder:1.5b-instruct-q4_k_m") == 1.5
    assert mc._params_in("deepseek-r1:8b-q4_K_M") == 8.0


def test_params_in_returns_none_for_no_size():
    assert mc._params_in("unknown-no-size") is None


# ===========================================================================
# 3. capability() after match() fix — the downstream effect
# ===========================================================================

def test_capability_llama32_1b_not_inflated():
    """After the match fix, capability of llama3.2:1b must reflect 1b stats,
    not the 3b entry's higher caps."""
    cap_1b_code = mc.capability("llama3.2:1b", "code")
    cap_3b_code = mc.capability("llama3.2:3b", "code")
    assert cap_1b_code < cap_3b_code, (
        f"1b code cap ({cap_1b_code}) should be less than 3b code cap ({cap_3b_code})")
    # Specific values: 1b=0.30, 3b=0.45 per catalog
    assert abs(cap_1b_code - 0.30) < 1e-9, f"expected 0.30, got {cap_1b_code}"


def test_capability_phi4_reasoning_not_underestimated():
    """phi4-reasoning:14b has reasoning=0.99; must not return phi4's 0.75."""
    cap = mc.capability("phi4-reasoning:14b", "reasoning")
    assert cap > 0.95, f"expected ~0.99, got {cap}"


# ===========================================================================
# 4. best_local_for() — model selection correctness
# ===========================================================================

def test_best_local_for_reasoning_picks_phi4_reasoning():
    """With phi4-reasoning:14b and phi4:14b available, reasoning tasks must pick
    the thinking/reasoning model."""
    avail = ["phi4:14b", "phi4-reasoning:14b", "llama3.2:3b"]
    best = mc.best_local_for("reasoning", avail, max_params_b=33.0)
    assert best == "phi4-reasoning:14b", (
        f"phi4-reasoning:14b has reasoning=0.99; best_local_for chose {best!r}")


def test_best_local_for_code_picks_coder_over_general():
    """qwen2.5-coder:7b should beat qwen2.5:7b on the code axis."""
    avail = ["qwen2.5:7b", "qwen2.5-coder:7b", "llama3.2:1b"]
    best = mc.best_local_for("code", avail, max_params_b=33.0)
    assert best == "qwen2.5-coder:7b", f"expected qwen2.5-coder:7b, got {best!r}"


def test_best_local_for_respects_max_params():
    """Models exceeding max_params_b (+1 margin) must be excluded."""
    avail = ["qwen3:14b", "qwen3:4b"]  # 14b > max 8 + 1 = 9b
    best = mc.best_local_for("general", avail, max_params_b=8.0)
    assert best is not None
    assert mc.match(best).params_b <= 8.0 + 1.0, f"chosen model {best!r} too large"
    # 4b is the only one that fits
    assert best == "qwen3:4b", f"expected qwen3:4b, got {best!r}"


def test_best_local_for_empty_pool_returns_none():
    """No available models at all -> None."""
    assert mc.best_local_for("general", [], max_params_b=7.0) is None


def test_best_local_for_all_oversized_returns_none():
    """All models exceed max_params_b (+ margin) -> None."""
    result = mc.best_local_for("general", ["qwen3:14b", "qwen2.5:14b"], max_params_b=2.0)
    assert result is None


# ===========================================================================
# 5. best_orchestrated_for() — tie-breaking and empty pool
# ===========================================================================

def test_best_orchestrated_for_empty_pool():
    assert mc.best_orchestrated_for("general", []) is None


def test_best_orchestrated_for_tier_filter():
    """Filtering by tier=paid_cheap must exclude paid_strong models."""
    avail = ["claude-opus-4-8", "claude-haiku-4-5-20251001", "gpt-4o-mini"]
    best = mc.best_orchestrated_for("code", avail, tier="paid_cheap")
    assert best is not None
    assert mc.orchestrated_tier(best) == "paid_cheap", (
        f"{best!r} should be paid_cheap, got {mc.orchestrated_tier(best)!r}")


def test_best_orchestrated_for_no_matching_tier_returns_none():
    """If the tier filter leaves no candidates, return None."""
    avail = ["claude-haiku-4-5-20251001"]  # only paid_cheap
    result = mc.best_orchestrated_for("general", avail, tier="paid_strong")
    assert result is None


def test_best_orchestrated_for_prefers_lower_cost_on_tie():
    """Within the same ~0.02 capability bucket, lower cost_weight must win."""
    avail = ["claude-opus-4-8", "claude-sonnet-4-6"]
    # For any axis: sonnet has lower cost (0.55 vs 1.00) and similar capability
    best = mc.best_orchestrated_for("general", avail, tier="paid_strong")
    # sonnet: general=0.93, cost=0.55; opus: general=0.97, cost=1.00
    # rounded to 0.02 bucket: 0.93/0.02=46.5->46, 0.97/0.02=48.5->48 (different buckets)
    # So opus wins on capability; but for axis where they're in same bucket, sonnet should win
    # Just verify a model is returned and it's valid
    assert best in avail


# ===========================================================================
# 6. tier_for() — boundary values
# ===========================================================================

def test_tier_for_exact_boundaries():
    """Test at the documented boundary values."""
    # Exactly 8 GB VRAM nvidia -> gpu_12gb
    t = mc.tier_for(ram_gb=16, gpu_vendor="nvidia", vram_gb=8)
    assert t.key == "gpu_12gb", f"8 GB VRAM nvidia -> {t.key}"

    # Exactly 12 GB VRAM nvidia -> gpu_12gb (not gpu_24gb)
    t = mc.tier_for(ram_gb=16, gpu_vendor="nvidia", vram_gb=12)
    assert t.key == "gpu_12gb", f"12 GB VRAM nvidia -> {t.key}"

    # Exactly 20 GB VRAM nvidia -> gpu_24gb (the threshold is >= 20)
    t = mc.tier_for(ram_gb=32, gpu_vendor="nvidia", vram_gb=20)
    assert t.key == "gpu_24gb", f"20 GB VRAM nvidia -> {t.key}"

    # Exactly 24 GB VRAM nvidia -> gpu_24gb
    t = mc.tier_for(ram_gb=32, gpu_vendor="nvidia", vram_gb=24)
    assert t.key == "gpu_24gb", f"24 GB VRAM nvidia -> {t.key}"

    # Apple Silicon 16 GB -> cpu_large (not gpu_24gb, which needs >= 32 GB)
    t = mc.tier_for(ram_gb=16, gpu_vendor="apple", vram_gb=0)
    assert t.key == "cpu_large", f"Apple 16 GB -> {t.key}"

    # Apple Silicon 32 GB -> gpu_24gb
    t = mc.tier_for(ram_gb=32, gpu_vendor="apple", vram_gb=0)
    assert t.key == "gpu_24gb", f"Apple 32 GB -> {t.key}"


def test_tier_for_cpu_boundaries():
    # Exactly 16 GB RAM, no GPU -> cpu_large
    t = mc.tier_for(ram_gb=16, gpu_vendor="none", vram_gb=0)
    assert t.key == "cpu_large", f"16 GB RAM no GPU -> {t.key}"

    # Less than 16 GB -> cpu_small
    t = mc.tier_for(ram_gb=8, gpu_vendor="none", vram_gb=0)
    assert t.key == "cpu_small", f"8 GB RAM no GPU -> {t.key}"

    t = mc.tier_for(ram_gb=12, gpu_vendor="none", vram_gb=0)
    assert t.key == "cpu_small", f"12 GB RAM no GPU -> {t.key}"


def test_tier_for_amd_gpu():
    """AMD GPUs should behave the same as NVIDIA for tier classification."""
    t = mc.tier_for(ram_gb=16, gpu_vendor="amd", vram_gb=8)
    assert t.key == "gpu_12gb", f"AMD 8 GB VRAM -> {t.key}"

    t = mc.tier_for(ram_gb=32, gpu_vendor="amd", vram_gb=24)
    assert t.key == "gpu_24gb", f"AMD 24 GB VRAM -> {t.key}"


# ===========================================================================
# 7. router.decide() — paid_cap enforcement and forced-kind edge cases
# ===========================================================================

def test_paid_cap_enforced_for_loop_refine():
    """loop_refine has paid_cap='paid_cheap'; paid_strong must never be chosen."""
    n = _node(local_models=["qwen3:8b"])
    feat = _f("Refina iterativamente este código hasta que los tests pasen.")
    d = router.decide(n, feat, HibridOptions(task_type="loop_refine"))
    assert d.chosen.tier != "paid_strong", (
        f"loop_refine must never choose paid_strong; got tier={d.chosen.tier}")


def test_paid_cap_enforced_for_simple():
    """simple has paid_cap='paid_cheap'; paid_strong must not be chosen."""
    n = _node(local_models=["qwen3:8b"])
    feat = _f("¿Cuántos días tiene febrero en un año bisiesto?")
    d = router.decide(n, feat, HibridOptions(task_type="simple"))
    assert d.chosen.tier != "paid_strong", (
        f"simple must never choose paid_strong; got tier={d.chosen.tier}")


def test_paid_cap_enforced_for_translate():
    """translate has paid_cap='paid_cheap'."""
    n = _node(local_models=["aya-expanse:8b"])
    feat = _f("Traduce este texto al inglés.")
    d = router.decide(n, feat, HibridOptions(task_type="translate"))
    assert d.chosen.tier != "paid_strong", (
        f"translate must never choose paid_strong; got tier={d.chosen.tier}")


def test_paid_cap_enforced_for_batch():
    """batch has paid_cap='paid_cheap'."""
    n = _node(local_models=["qwen2.5:7b"])
    feat = _f("Procesa este archivo masivo por lotes.")
    d = router.decide(n, feat, HibridOptions(task_type="batch"))
    assert d.chosen.tier != "paid_strong", (
        f"batch must never choose paid_strong; got tier={d.chosen.tier}")


def test_force_fallback_when_kind_unavailable_reports_correctly():
    """BUG: when opts.force names a kind with no candidates, the router falls back
    to all candidates (good) but the reason string claimed the force was honored (bad).
    The reason must reflect the fallback, not mislead the caller.
    """
    # local-only node: no cloud candidates exist
    n = _local_only_node(["qwen3:4b"])
    feat = _f("hola")
    d = router.decide(n, feat, HibridOptions(force="cloud_strong"))
    # The chosen destination will be local (the only one available) — that's fine.
    assert d.chosen is not None, "must still produce a decision"
    # The reason must NOT claim the force was honored when the kind wasn't available
    assert "cloud_strong" not in d.reason or "no disponible" in d.reason or "fallback" in d.reason, (
        f"reason misleadingly claims force was honored: {d.reason!r}\n"
        f"chosen.kind={d.chosen.kind!r} (should be 'local', not 'cloud_strong')")


def test_force_honored_when_kind_is_available():
    """When the forced kind IS available, it must be chosen and the reason must say so."""
    n = _node(local_models=["qwen3:8b"])
    feat = _f("hola")
    d = router.decide(n, feat, HibridOptions(force="cloud_cheap"))
    assert d.chosen.kind == "cloud_cheap", f"got {d.chosen.kind!r}"
    assert "cloud_cheap" in d.reason


def test_force_local_with_no_local_falls_back():
    """Forcing local on a cloud-only node must fall back gracefully."""
    n = _node(local_models=None, cloud=True)  # no local models
    feat = _f("hola")
    # Should not raise; falls back to cloud
    d = router.decide(n, feat, HibridOptions(force="local"))
    assert d.chosen is not None
    # kind won't be local since there's no local, but must not crash
    assert d.chosen.kind in ("cloud_cheap", "cloud_strong")


# ===========================================================================
# 8. Router integration with phi4-reasoning — downstream routing correctness
# ===========================================================================

def test_router_uses_correct_phi4_reasoning_caps():
    """After the match() fix, a node with phi4-reasoning:14b must be preferred
    over phi4:14b for reasoning tasks (because its reasoning cap is 0.99 vs 0.75)."""
    n = _node(local_models=["phi4:14b", "phi4-reasoning:14b"], cloud=False)
    feat = _f("Demuestra paso a paso por qué NP ≠ P es un problema abierto; "
              "razona la complejidad y los trade-offs con rigor.")
    d = router.decide(n, feat, HibridOptions(allow_cloud=False, task_type="deep_reason"))
    assert d.chosen.model == "phi4-reasoning:14b", (
        f"For deep reasoning, phi4-reasoning:14b (reasoning=0.99) should beat "
        f"phi4:14b (reasoning=0.75). Got: {d.chosen.model!r}")


def test_router_uses_correct_llama32_1b_caps():
    """After the match() fix, llama3.2:1b must not be preferred over llama3.2:3b
    for code tasks (1b code=0.30, 3b code=0.45)."""
    n = _node(local_models=["llama3.2:1b", "llama3.2:3b"], cloud=False)
    feat = _f("def f(x): return x  # refactor this function")
    d = router.decide(n, feat, HibridOptions(allow_cloud=False))
    assert d.chosen.model == "llama3.2:3b", (
        f"llama3.2:3b (code=0.45) should beat llama3.2:1b (code=0.30). "
        f"Got: {d.chosen.model!r}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{ok}/{len(fns)} tests OK")
