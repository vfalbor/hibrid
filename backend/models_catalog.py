"""Catálogo curado de modelos locales: qué se sabe que funciona aceptablemente,
tanto por encaje en la máquina como por competencia en la TAREA.

El mapeo modelo/máquina no puede ser sólo "¿cabe en memoria?": un modelo de 1B cabe
en casi todo pero no sirve para código serio. Aquí registramos, por modelo pequeño
conocido, su competencia por eje de tarea (general / code / reasoning), su tamaño y
RAM aproximada en Q4, y enlaces (Hugging Face + Ollama). Las puntuaciones son priors
basados en benchmarks/reputación públicos (HF leaderboards, EvalPlus/HumanEval para
código, reputación de cada familia); se afinan con el histórico real del nodo.

Ejes de tarea -> qué capability se mira:
  code/has_code        -> "code"
  deep_reason          -> "reasoning"
  resto (general/...)  -> "general"
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    family: str           # familia para emparejar con el tag de ollama
    params_b: float
    ram_q4_gb: float      # RAM/VRAM aprox en Q4_K_M (pesos + KV pequeño)
    caps: dict            # {"general":x,"code":y,"reasoning":z} en 0..1
    hf: str
    ollama: str
    note: str = ""


# Catálogo de modelos pequeños "conocidos buenos" para CPU/edge y GPUs modestas.
CATALOG: list[ModelInfo] = [
    ModelInfo("qwen2.5-coder:7b", 7.0, 5.0, {"general": 0.72, "code": 0.82, "reasoning": 0.66},
              "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:7b", "Especialista en código."),
    ModelInfo("qwen2.5-coder:1.5b", 1.5, 1.1, {"general": 0.56, "code": 0.66, "reasoning": 0.46},
              "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:1.5b", "Código fuerte para su tamaño."),
    ModelInfo("qwen2.5:7b", 7.0, 5.0, {"general": 0.76, "code": 0.70, "reasoning": 0.68},
              "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
              "https://ollama.com/library/qwen2.5:7b", "Generalista sólido 7B."),
    ModelInfo("qwen2.5:3b", 3.0, 2.2, {"general": 0.66, "code": 0.60, "reasoning": 0.56},
              "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct",
              "https://ollama.com/library/qwen2.5:3b"),
    ModelInfo("qwen2.5:1.5b", 1.5, 1.0, {"general": 0.55, "code": 0.50, "reasoning": 0.45},
              "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct",
              "https://ollama.com/library/qwen2.5:1.5b"),
    ModelInfo("qwen2.5:0.5b", 0.5, 0.6, {"general": 0.38, "code": 0.30, "reasoning": 0.28},
              "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
              "https://ollama.com/library/qwen2.5:0.5b", "Sólo tareas muy cortas/clasificación."),
    ModelInfo("llama3.1:8b", 8.0, 5.5, {"general": 0.75, "code": 0.62, "reasoning": 0.68},
              "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
              "https://ollama.com/library/llama3.1:8b"),
    ModelInfo("llama3.2:3b", 3.0, 2.0, {"general": 0.62, "code": 0.45, "reasoning": 0.48},
              "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct",
              "https://ollama.com/library/llama3.2:3b"),
    ModelInfo("llama3.2:1b", 1.0, 1.3, {"general": 0.45, "code": 0.30, "reasoning": 0.30},
              "https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct",
              "https://ollama.com/library/llama3.2:1b", "Rápido; clasificar/extraer/resumir corto."),
    ModelInfo("phi3.5:3.8b", 3.8, 2.6, {"general": 0.66, "code": 0.55, "reasoning": 0.70},
              "https://huggingface.co/microsoft/Phi-3.5-mini-instruct",
              "https://ollama.com/library/phi3.5", "Razonamiento alto para su tamaño."),
    ModelInfo("gemma2:2b", 2.0, 1.7, {"general": 0.58, "code": 0.40, "reasoning": 0.46},
              "https://huggingface.co/google/gemma-2-2b-it",
              "https://ollama.com/library/gemma2:2b"),
]


def _params_in(name: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", name.lower())
    return float(m.group(1)) if m else None


def match(model_name: str) -> ModelInfo | None:
    """Empareja un tag de ollama (p.ej. 'qwen2.5:1.5b-instruct-q4') con el catálogo."""
    n = model_name.lower()
    # 1) familia + tamaño exactos
    for e in CATALOG:
        fam, size = e.family.split(":")
        if fam in n and (size.replace("b", "") in n or _params_in(n) == e.params_b):
            return e
    # 2) sólo familia base (sin tamaño)
    for e in CATALOG:
        if e.family.split(":")[0] in n:
            return e
    return None


def capability(model_name: str, axis: str = "general") -> float:
    e = match(model_name)
    if e:
        return e.caps.get(axis, e.caps.get("general", 0.5))
    # Fallback genérico por tamaño si no está en catálogo.
    p = _params_in(model_name) or 7.0
    base = min(0.9, 0.40 + 0.10 * (p ** 0.5))
    return base if axis == "general" else base * 0.85


def axis_for_task(task_type: str, has_code: bool) -> str:
    if has_code or task_type in ("loop_refine", "loop_verify"):
        return "code"
    if task_type == "deep_reason":
        return "reasoning"
    return "general"


def best_local_for(axis: str, available: list[str], max_params_b: float) -> str | None:
    """Mejor modelo DISPONIBLE que cabe en la máquina y es competente en el eje dado."""
    scored = []
    for m in available:
        e = match(m)
        params = e.params_b if e else (_params_in(m) or 7.0)
        if params <= max_params_b + 1.0:  # margen
            scored.append((capability(m, axis), -params, m))  # cap alta, luego menor params
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]
