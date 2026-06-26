"""Perfiles de ejecución por TIPO DE TAREA (la "otra pensada").

El routing no se guía sólo por la complejidad de una consulta suelta, sino por el
*tipo de tarea* y su *patrón de ejecución*. Caso estrella: los LOOPS (refinar código,
QA iterativo) son muchas llamadas de bajo coste unitario pero enorme volumen → deben ir
**local-first** y escalar con cuentagotas, nunca a tokens caros por iteración.

Abstracción de TIERS (mapeo libre/local <-> pago):
  - local_free  : modelos open-weights en la máquina del usuario (coste ~0, privacidad máx).
  - paid_cheap  : modelos de pago de bajo coste de token (Haiku, gpt-4o-mini...).
  - paid_strong : modelos de pago top (Opus, gpt-4o...) — caros, sólo cuando aporta.
  - remote_local: (futuro) otra máquina del usuario con open-weights por red/SSH.

Un PERFIL define el orden de preferencia de tiers, un bonus de utilidad por tier
(p.ej. subvencionar lo local en loops), si se permite paid_strong, y la política de
escalado. Un *skill* o agente declara su task_type/profile; si no, se infiere.
Los perfiles son **contribuibles por la comunidad** (Policy Registry del hub).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Mapeo kind interno -> tier de coste/licencia.
KIND_TO_TIER = {
    "local": "local_free",
    "cloud_cheap": "paid_cheap",
    "cloud_strong": "paid_strong",
}


@dataclass
class ExecutionProfile:
    name: str
    # Tiers permitidos, en orden de preferencia (los no listados quedan excluidos).
    tier_order: list[str]
    # Bonus de utilidad por tier (subvenciona/penaliza tiers para forzar la política).
    tier_bonus: dict[str, float] = field(default_factory=dict)
    # Overrides de las perillas lambda (None = usar las del settings/petición).
    lambda_cost: float | None = None
    lambda_lat: float | None = None
    lambda_priv: float | None = None
    # Tier máximo al que la CASCADA puede escalar tras baja confianza local.
    escalate_to: str = "paid_strong"
    # Iteraciones de baja confianza consecutivas antes de escalar (loops: >1).
    escalate_after: int = 1
    description: str = ""


# --- Perfiles incorporados (de fábrica) ---
BUILTIN: dict[str, ExecutionProfile] = {
    # Loops de refinado/QA: local-first agresivo; NO paid_strong por iteración.
    "loop_refine": ExecutionProfile(
        name="loop_refine",
        tier_order=["local_free", "paid_cheap"],
        tier_bonus={"local_free": 0.6, "paid_cheap": 0.0},
        escalate_to="paid_cheap",     # como mucho a barato; nunca caro en el bucle
        escalate_after=3,             # tolera fallos locales antes de salir
        description="Bucle iterativo (refinar código, QA). Quema cómputo local/gratis.",
    ),
    # Pase de verificación FINAL de un loop: aquí sí se permite el modelo top.
    "loop_verify": ExecutionProfile(
        name="loop_verify",
        tier_order=["paid_strong", "paid_cheap", "local_free"],
        tier_bonus={"paid_strong": 0.3},
        escalate_to="paid_strong",
        escalate_after=1,
        description="Verificación final única de un loop: calidad por encima de coste.",
    ),
    # Razonamiento profundo de una sola llamada: calidad manda.
    "deep_reason": ExecutionProfile(
        name="deep_reason",
        tier_order=["paid_strong", "local_free", "paid_cheap"],
        tier_bonus={"paid_strong": 0.2},
        escalate_to="paid_strong",
        escalate_after=1,
        description="Tarea compleja de una sola llamada (arquitectura, prueba, debug duro).",
    ),
    # Tareas triviales: local primero, barato si no; nunca el modelo caro.
    "simple": ExecutionProfile(
        name="simple",
        tier_order=["local_free", "paid_cheap"],
        tier_bonus={"local_free": 0.4},
        escalate_to="paid_cheap",
        escalate_after=1,
        description="Clasificar, extraer, traducir, resúmenes cortos.",
    ),
    # Interactivo: local sólo si es rápido (el router ya penaliza tok/s bajo); si no, barato.
    "interactive": ExecutionProfile(
        name="interactive",
        tier_order=["local_free", "paid_cheap", "paid_strong"],
        tier_bonus={"local_free": 0.2},
        lambda_lat=0.8,               # la latencia pesa más
        escalate_to="paid_cheap",
        escalate_after=1,
        description="Chat en vivo: prioriza latencia.",
    ),
    # Batch/offline: sin presión de latencia -> maximiza local aunque sea lento.
    "batch": ExecutionProfile(
        name="batch",
        tier_order=["local_free", "paid_cheap"],
        tier_bonus={"local_free": 1.0},
        lambda_lat=0.0,               # da igual la latencia
        escalate_to="paid_cheap",
        escalate_after=5,
        description="Procesado masivo sin urgencia: todo lo posible en local.",
    ),
    # Por defecto: comportamiento equilibrado (función de utilidad pura).
    "general": ExecutionProfile(
        name="general",
        tier_order=["local_free", "paid_cheap", "paid_strong"],
        description="Equilibrado: argmax U(d) sin sesgo de tipo de tarea.",
    ),
}


def get_profile(name: str | None) -> ExecutionProfile:
    return BUILTIN.get(name or "general", BUILTIN["general"])


def profile_for_task_type(task_type: str | None) -> ExecutionProfile:
    """task_type y nombre de perfil coinciden en los de fábrica; extensible por el hub."""
    return get_profile(task_type)
