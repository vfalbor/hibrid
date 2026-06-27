"""Registro de modelos disponibles + micro-benchmark de arranque.

- Detecta qué modelos LOCALES hay (vía API OpenAI-compat) y qué modelos de NUBE tiene
  el usuario (según claves configuradas).
- Mide tok/s reales por modelo local con un micro-benchmark y lo cachea por nodo
  (recomendación estrella de BenchAgent: nadie más enruta por velocidad medida real).
- Mantiene priors de coste ($/1M tokens) y calidad por destino.
"""
from __future__ import annotations

import json
import os
import time

import httpx

from . import providers
from .config import settings
from .profiler import HardwareProfile, detect

# Priors de calidad base por tamaño de modelo local (0..1). Ajustables online.
def _local_quality(params_b: float, complexity: float) -> float:
    # Modelos grandes ~ mejor; penaliza tareas complejas en modelos pequeños.
    cap = min(1.0, 0.45 + 0.10 * (params_b ** 0.5))     # 3B~0.62, 8B~0.73, 70B~0.93
    return max(0.05, cap - complexity * (1.0 - cap) * 1.2)


# Coste aproximado $/1M tokens de salida (priors; se pueden sobreescribir por .env).
CLOUD_COST = {
    "claude-opus-4-8": 15.0,
    "claude-haiku-4-5-20251001": 1.0,
    "gpt-4o": 10.0,
    "gpt-4o-mini": 0.6,
}
CLOUD_QUALITY = {
    "claude-opus-4-8": 0.98,
    "claude-haiku-4-5-20251001": 0.85,
    "gpt-4o": 0.95,
    "gpt-4o-mini": 0.80,
}


class NodeProfile:
    def __init__(self, hardware: HardwareProfile):
        self.hardware = hardware
        self.local_endpoint: str | None = None
        self.local_models: list[str] = []
        self.local_default: str | None = None
        self.tok_s: dict[str, float] = {}   # modelo local -> tok/s medidos
        self.cloud_models: list[str] = []    # modelos orquestados servibles (sin API key)
        self.backends: list = []             # backends de orquestación descubiertos

    def to_dict(self) -> dict:
        return {
            "hardware": self.hardware.to_dict(),
            "local_endpoint": self.local_endpoint,
            "local_models": self.local_models,
            "local_default": self.local_default,
            "tok_s": self.tok_s,
            "cloud_models": self.cloud_models,
            "backends": [
                {"id": b.id, "mechanism": b.mechanism, "agent": b.agent,
                 "available": b.available, "models": b.models, "latency_s": b.latency_s}
                for b in self.backends
            ],
        }


def _estimate_params_b(model_name: str) -> float:
    """Extrae el tamaño en B de nombres tipo 'qwen2.5:7b', 'llama3.2:3b-instruct-q4'."""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", model_name.lower())
    if m:
        return float(m.group(1))
    return 7.0  # por defecto asume ~7B


def _discover_orchestration(np: "NodeProfile") -> None:
    """Puebla np.backends y np.cloud_models con la capa de orquestación disponible."""
    from . import backends as backends_mod
    np.backends = backends_mod.discover_backends()
    np.cloud_models = backends_mod.available_orchestrated_models(np.backends)


async def _micro_benchmark(endpoint: str, model: str) -> float:
    """Mide tok/s reales con un prompt corto. Devuelve 0 si falla."""
    try:
        res = await providers.generate_local(
            endpoint, model,
            [{"role": "user", "content": "Cuenta del 1 al 20 separando por comas."}],
            temperature=0.0, max_tokens=64,
        )
        return round(res.tok_s, 1)
    except Exception:
        return 0.0


async def build_node_profile(use_cache: bool = True, benchmark: bool = True) -> NodeProfile:
    # Cache para no re-medir en cada arranque.
    if use_cache and os.path.exists(settings.cache_path):
        try:
            with open(settings.cache_path) as f:
                d = json.load(f)
            hw = HardwareProfile(**d["hardware"])
            np = NodeProfile(hw)
            np.local_endpoint = d.get("local_endpoint")
            np.local_models = d.get("local_models", [])
            np.local_default = d.get("local_default")
            np.tok_s = d.get("tok_s", {})
            # Los backends (qué agentes hay logueados) se RE-DESCUBREN siempre: es barato
            # y puede cambiar entre arranques sin tener que re-medir el hardware.
            _discover_orchestration(np)
            return np
        except Exception:
            pass

    hw = detect()
    np = NodeProfile(hw)

    endpoint, models = await providers.list_local_models()
    np.local_endpoint, np.local_models = endpoint, models

    # Tier de pago SIN API key: se descubren los backends de orquestación disponibles
    # (claude/codex/opencode/copilot logueados, servicio de skills, passthrough).
    _discover_orchestration(np)

    # Micro-benchmark de los modelos locales -> tok/s real.
    if benchmark and endpoint and models:
        # Elegir el mayor modelo que la máquina puede ejecutar como default local.
        usable = [m for m in models if _estimate_params_b(m) <= hw.max_local_params_b + 1]
        for m in (usable or models)[:4]:   # no benchmarkear más de 4 por arranque
            tps = await _micro_benchmark(endpoint, m)
            if tps > 0:
                np.tok_s[m] = tps
        if np.tok_s:
            # default = modelo válido más capaz (mayor params) con tok/s >= mínimo.
            ok = [m for m in np.tok_s if np.tok_s[m] >= settings.min_local_tps]
            pool = ok or list(np.tok_s)
            np.local_default = max(pool, key=_estimate_params_b)

    if use_cache:
        try:
            with open(settings.cache_path, "w") as f:
                json.dump(np.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return np


# Helpers de coste/calidad usados por el router.
def local_quality(model: str, complexity: float, axis: str = "general") -> float:
    # Calidad = competencia conocida del modelo en el eje de la tarea (catálogo curado),
    # degradada por la complejidad (un modelo pequeño sufre más en tareas difíciles).
    from .models_catalog import capability
    cap = capability(model, axis)
    return max(0.05, cap - complexity * (1.0 - cap) * 0.8)


def cloud_cost(model: str) -> float:
    return CLOUD_COST.get(model, 5.0)


def cloud_quality(model: str) -> float:
    return CLOUD_QUALITY.get(model, 0.9)


def params_b(model: str) -> float:
    return _estimate_params_b(model)
