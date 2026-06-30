"""Tests unitarios del classifier (sin red, sin LLM).

Cubre: la corrección del bug deep_reason texto-puro, y regresiones para
write / translate / simple / code / loop_refine / loop_verify.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import classifier
from backend.schemas import ChatMessage


def _classify(text: str):
    return classifier.classify([ChatMessage(role="user", content=text)])


# ---------------------------------------------------------------------------
# Bug fix: texto-puro con múltiples señales hard → deep_reason (no "general")
# ---------------------------------------------------------------------------

def test_text_only_hard_reasoning_is_deep_reason():
    """BUG FIX: prompt texto-puro con ≥3 señales hard debe clasificarse deep_reason."""
    feat = _classify(
        "Diseña la arquitectura distribuida y razona los trade-offs paso a paso, "
        "demuestra la complejidad."
    )
    assert feat.task_type == "deep_reason", (
        f"Esperado deep_reason, obtenido {feat.task_type!r} "
        f"(complexity={feat.complexity})"
    )


def test_dijkstra_reasoning_is_deep_reason():
    """Prompt clásico de razonamiento algorítmico sin código → deep_reason."""
    feat = _classify(
        "Demuestra paso a paso por qué el algoritmo de Dijkstra es óptimo y "
        "analiza su complejidad; deriva la cota y razona el trade-off."
    )
    assert feat.task_type == "deep_reason", (
        f"Esperado deep_reason, obtenido {feat.task_type!r}"
    )


# ---------------------------------------------------------------------------
# Regresiones: cada tipo canónico debe seguir clasificándose igual
# ---------------------------------------------------------------------------

def test_write_regression():
    """Redacción de artículo → write (no deep_reason)."""
    feat = _classify("Redáctame un artículo de blog sobre routing de LLMs.")
    assert feat.task_type == "write", (
        f"Esperado write, obtenido {feat.task_type!r}"
    )


def test_translate_regression():
    """Traducción simple → translate."""
    feat = _classify("Traduce esto al inglés.")
    assert feat.task_type == "translate", (
        f"Esperado translate, obtenido {feat.task_type!r}"
    )


def test_simple_classify_email():
    """Clasificar un email → simple."""
    feat = _classify("Clasifica este email como spam o no.")
    assert feat.task_type == "simple", (
        f"Esperado simple, obtenido {feat.task_type!r}"
    )


def test_simple_time_question():
    """Pregunta trivial → simple."""
    feat = _classify("¿Qué hora es en Tokio?")
    assert feat.task_type == "simple", (
        f"Esperado simple, obtenido {feat.task_type!r}"
    )


def test_simple_greeting():
    """Saludo corto → no debe ser deep_reason."""
    feat = _classify("Hola, ¿cómo estás?")
    assert feat.task_type != "deep_reason", (
        f"Un saludo no debe ser deep_reason, obtenido {feat.task_type!r}"
    )


def test_code_regression():
    """Función Python corta → code."""
    feat = _classify("def f(x): return x  # arregla")
    assert feat.task_type == "code", (
        f"Esperado code, obtenido {feat.task_type!r}"
    )


def test_loop_refine_regression():
    """Bucle de refinado → loop_refine."""
    feat = _classify("refactoriza iterativamente hasta que pasen los tests")
    assert feat.task_type == "loop_refine", (
        f"Esperado loop_refine, obtenido {feat.task_type!r}"
    )


def test_loop_verify_regression():
    """Verificación final → loop_verify."""
    feat = _classify("verificación final y aprueba el resultado.")
    assert feat.task_type == "loop_verify", (
        f"Esperado loop_verify, obtenido {feat.task_type!r}"
    )


# ---------------------------------------------------------------------------
# Sanity: complejidad y has_code se calculan correctamente
# ---------------------------------------------------------------------------

def test_code_prompt_has_code_flag():
    feat = _classify("```python\ndef hello():\n    print('hi')\n```")
    assert feat.has_code


def test_simple_prompt_no_code_flag():
    feat = _classify("¿Cuál es la capital de Francia?")
    assert not feat.has_code


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
