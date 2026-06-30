"""task_policy — el mapeo EXPLÍCITO de "qué LLM por tipo de tarea".

Antes, esta decisión estaba repartida: el classifier infería un task_type, profiles.py
daba el orden de tiers, models_catalog elegía el modelo local por eje, y config fijaba
un modelo de nube. Aquí se consolida en UNA tabla legible y auditable:

    task_type -> (axis, tier ladder, preferencia de modelo por tier)

- `axis` ("general"|"code"|"reasoning") selecciona qué competencia se mira tanto en
  modelos LOCALES (models_catalog.capability) como ORQUESTADOS (orchestrated_capability).
- `tier_ladder` documenta la escalera de coste preferida para ese tipo de tarea (la
  política de runtime — bonus de tier, λ, escalado — vive en profiles.py y es coherente
  con esta tabla).
- La elección del modelo concreto dentro de un tier la hace el router con el catálogo por
  eje (best_local_for / best_orchestrated_for), no se fija a mano aquí.

Esta tabla es la "fuente de la verdad" que se renderiza también en la documentación.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskPolicy:
    task_type: str
    axis: str                       # general | writing | code | reasoning | multilingual
    tier_ladder: list[str]          # tiers preferidos, de barato a caro
    rationale: str = ""
    # Tier máximo permitido para el modelo orquestado en esta tarea (None = sin tope).
    paid_cap: str | None = None     # "paid_cheap" -> nunca usar paid_strong


# La matriz. Coherente con profiles.BUILTIN (tier_order / escalate_to).
POLICIES: dict[str, TaskPolicy] = {
    "loop_refine": TaskPolicy(
        "loop_refine", "code", ["local_free", "paid_cheap"],
        "Bucle de refinado/QA: cientos de llamadas baratas. Local-first; nunca el modelo "
        "caro por iteración.", paid_cap="paid_cheap"),
    "loop_verify": TaskPolicy(
        "loop_verify", "code", ["paid_strong", "paid_cheap", "local_free"],
        "Verificación final única de un loop: calidad por encima de coste."),
    "deep_reason": TaskPolicy(
        "deep_reason", "reasoning", ["paid_strong", "local_free", "paid_cheap"],
        "Tarea dura de una sola llamada (arquitectura, prueba, debug profundo)."),
    "simple": TaskPolicy(
        "simple", "general", ["local_free", "paid_cheap"],
        "Clasificar, extraer, resumen corto.", paid_cap="paid_cheap"),
    "write": TaskPolicy(
        "write", "writing", ["local_free", "paid_cheap", "paid_strong"],
        "Redacción/copy/long-form: pide un modelo fuerte en escritura (eje 'writing'). "
        "Local-first; escala a pago si la pieza es larga o crítica."),
    "translate": TaskPolicy(
        "translate", "multilingual", ["local_free", "paid_cheap"],
        "Traducción/tarea multilingüe (español): prioriza modelos multilingües "
        "(Aya-Expanse, Qwen3). Local cubre la mayoría.", paid_cap="paid_cheap"),
    "code": TaskPolicy(
        "code", "code", ["local_free", "paid_cheap", "paid_strong"],
        "Generación de código de una sola pasada: eje 'code' (Qwen2.5-Coder local)."),
    "interactive": TaskPolicy(
        "interactive", "general", ["local_free", "paid_cheap", "paid_strong"],
        "Chat en vivo: la latencia pesa más (profiles sube λ_lat)."),
    "batch": TaskPolicy(
        "batch", "general", ["local_free", "paid_cheap"],
        "Procesado masivo sin urgencia: maximiza local.", paid_cap="paid_cheap"),
    "general": TaskPolicy(
        "general", "general", ["local_free", "paid_cheap", "paid_strong"],
        "Equilibrado: utilidad pura sin sesgo de tipo de tarea."),
}


def policy_for(task_type: str | None) -> TaskPolicy:
    return POLICIES.get(task_type or "general", POLICIES["general"])


def axis_for(task_type: str | None, has_code: bool = False) -> str:
    """Eje de la tarea: si hay código (o es un loop de código) se mira 'code';
    si no, el eje declarado en la matriz para ese task_type."""
    if has_code or task_type in ("loop_refine", "loop_verify"):
        return "code"
    return policy_for(task_type).axis


def axes() -> tuple[str, ...]:
    """Ejes distintos presentes en la matriz (para documentación/validación)."""
    return tuple(dict.fromkeys(p.axis for p in POLICIES.values()))


def as_table() -> list[dict]:
    """Renderiza la matriz como filas (para documentación / endpoint /v1/policy)."""
    return [
        {"task_type": p.task_type, "axis": p.axis,
         "tier_ladder": " → ".join(p.tier_ladder),
         "paid_cap": p.paid_cap or "—", "rationale": p.rationale}
        for p in POLICIES.values()
    ]
