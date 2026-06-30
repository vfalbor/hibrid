"""Catálogo curado de modelos locales: qué se sabe que funciona aceptablemente,
tanto por encaje en la máquina como por competencia en la TAREA.

El mapeo modelo/máquina no puede ser sólo "¿cabe en memoria?": un modelo de 1B cabe
en casi todo pero no sirve para código serio. Aquí registramos, por modelo pequeño
conocido, su competencia POR EJE DE TAREA, su tamaño y RAM aproximada en Q4, y enlaces
(Hugging Face + Ollama).

Ejes de tarea (caps en 0..1):
  general        conocimiento + seguir instrucciones (MMLU, IFEval, Arena-Hard)
  writing        redacción / copy / resumen / long-form (MT-Bench, EQ/creative, IFEval)
  code           generación de código (HumanEval+, BigCodeBench, LiveCodeBench)
  reasoning      razonamiento multipaso + matemáticas (GSM8K, MATH, GPQA, AIME)
  multilingual   calidad fuera del inglés (español) y traducción (FLORES, m-ArenaHard)

Las puntuaciones son priors normalizados (0..1) derivados de benchmarks públicos
(junio 2026). Fuentes principales por modelo en `note`/docs/MODELS.md:
  - Código: EvalPlus/HumanEval+, BigCodeBench, LiveCodeBench, Qwen2.5-Coder tech report.
  - General/redacción/multilingüe: Qwen2.5/Qwen3 reports, IFEval/MMLU, Aya-Expanse,
    Gemma2, BenchMAX multilingüe, La Leaderboard (español).
  - Razonamiento: DeepSeek-R1 distills (arXiv 2501.12948), Phi-4-reasoning
    (arXiv 2504.21318/2504.21233), Qwen3 thinking mode.
Se afinan online con el histórico real del nodo.

OJO con los modelos "thinking" (Qwen3 thinking, R1 distills, Phi-4-reasoning): su caps de
`reasoning` asume el modo de razonamiento ACTIVO, que cuesta 2-5x tokens y latencia. Para
chat/redacción rápida usan modo normal (caps general/writing aquí ya reflejan ese modo).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Ejes soportados (orden canónico).
AXES = ("general", "writing", "code", "reasoning", "multilingual")


@dataclass(frozen=True)
class ModelInfo:
    family: str           # familia:tamaño para emparejar con el tag de ollama
    params_b: float
    ram_q4_gb: float      # RAM/VRAM aprox en Q4_K_M (pesos + KV pequeño @2K ctx)
    caps: dict            # {eje: 0..1} para los ejes de AXES
    hf: str
    ollama: str
    note: str = ""
    thinking: bool = False  # razona con cadena-de-pensamiento (coste 2-5x tokens/latencia)


def _c(general=0.5, writing=None, code=0.4, reasoning=0.3, multilingual=0.45) -> dict:
    """Atajo: writing por defecto = general - 0.04 (redactar pide algo más que conocer)."""
    return {"general": general, "writing": general - 0.04 if writing is None else writing,
            "code": code, "reasoning": reasoning, "multilingual": multilingual}


# Catálogo de modelos pequeños "conocidos buenos" para CPU/edge y GPUs modestas.
# RAM Q4 según tabla de footprint (params × 0.6 GB/B + ~10% overhead, KV @2K ctx aparte).
CATALOG: list[ModelInfo] = [
    # --- Qwen2.5-Coder (especialistas en código; rey por tamaño hasta 14B) ---
    ModelInfo("qwen2.5-coder:32b", 32.0, 20.0,
              _c(general=0.80, writing=0.74, code=0.97, reasoning=0.50, multilingual=0.64),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:32b",
              "HumanEval+~88, LCB~45. Mejor coder local; pide 24GB VRAM."),
    ModelInfo("qwen2.5-coder:14b", 14.0, 8.7,
              _c(general=0.74, writing=0.70, code=0.90, reasoning=0.45, multilingual=0.60),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:14b",
              "HumanEval+ 87.2, BCB-C 48.4, LCB 37.1. Mejor coder <16B."),
    ModelInfo("qwen2.5-coder:7b", 7.0, 4.5,
              _c(general=0.66, writing=0.62, code=0.79, reasoning=0.30, multilingual=0.55),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:7b",
              "HumanEval+ 84.1, BCB-C 41.0. El mejor coder que cabe en 8GB."),
    ModelInfo("qwen2.5-coder:3b", 3.0, 1.9,
              _c(general=0.55, writing=0.50, code=0.67, reasoning=0.22, multilingual=0.45),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:3b", "HumanEval+ 80.5."),
    ModelInfo("qwen2.5-coder:1.5b", 1.5, 1.2,
              _c(general=0.45, writing=0.40, code=0.54, reasoning=0.18, multilingual=0.35),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:1.5b", "Código fuerte para su tamaño."),
    ModelInfo("qwen2.5-coder:0.5b", 0.5, 0.4,
              _c(general=0.30, writing=0.25, code=0.15, reasoning=0.10, multilingual=0.18),
              "https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct",
              "https://ollama.com/library/qwen2.5-coder:0.5b", "Sólo tareas triviales."),

    # --- Qwen3 (generalistas/redacción top <14B; modo thinking para razonar) ---
    ModelInfo("qwen3:14b", 14.0, 8.7,
              _c(general=0.88, writing=0.85, code=0.80, reasoning=0.81, multilingual=0.80),
              "https://huggingface.co/Qwen/Qwen3-14B",
              "https://ollama.com/library/qwen3:14b",
              "119 idiomas. reasoning=modo thinking (~0.64 sin él).", thinking=True),
    ModelInfo("qwen3:8b", 8.0, 5.0,
              _c(general=0.90, writing=0.88, code=0.74, reasoning=0.70, multilingual=0.78),
              "https://huggingface.co/Qwen/Qwen3-8B",
              "https://ollama.com/library/qwen3:8b",
              "Mejor redactor/seguir-instrucciones <14B (IFEval 85, MMLU 85.9). "
              "reasoning=thinking (~0.52 sin él).", thinking=True),
    ModelInfo("qwen3:4b", 4.0, 3.0,
              _c(general=0.84, writing=0.80, code=0.60, reasoning=0.45, multilingual=0.72),
              "https://huggingface.co/Qwen/Qwen3-4B",
              "https://ollama.com/library/qwen3:4b",
              "IFEval 81.9. El mejor en ≤4GB para redacción/español.", thinking=True),

    # --- Qwen2.5 generalistas ---
    ModelInfo("qwen2.5:14b", 14.0, 8.7,
              _c(general=0.83, writing=0.80, code=0.70, reasoning=0.31, multilingual=0.62),
              "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct",
              "https://ollama.com/library/qwen2.5:14b", "MT-Bench 8.88; gran redactor 14B."),
    ModelInfo("qwen2.5:7b", 7.0, 4.5,
              _c(general=0.74, writing=0.70, code=0.60, reasoning=0.28, multilingual=0.58),
              "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
              "https://ollama.com/library/qwen2.5:7b", "Generalista sólido y muy probado."),
    ModelInfo("qwen2.5:3b", 3.0, 1.9,
              _c(general=0.50, writing=0.48, code=0.55, reasoning=0.20, multilingual=0.45),
              "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct",
              "https://ollama.com/library/qwen2.5:3b"),
    ModelInfo("qwen2.5:1.5b", 1.5, 1.2,
              _c(general=0.37, writing=0.33, code=0.50, reasoning=0.18, multilingual=0.30),
              "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct",
              "https://ollama.com/library/qwen2.5:1.5b"),
    ModelInfo("qwen2.5:0.5b", 0.5, 0.4,
              _c(general=0.30, writing=0.22, code=0.20, reasoning=0.10, multilingual=0.18),
              "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
              "https://ollama.com/library/qwen2.5:0.5b", "Sólo clasificación/tareas muy cortas."),

    # --- Llama ---
    ModelInfo("llama3.1:8b", 8.0, 5.0,
              _c(general=0.72, writing=0.68, code=0.51, reasoning=0.14, multilingual=0.50),
              "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct",
              "https://ollama.com/library/llama3.1:8b"),
    ModelInfo("llama3.2:3b", 3.0, 2.0,
              _c(general=0.64, writing=0.60, code=0.45, reasoning=0.20, multilingual=0.45),
              "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct",
              "https://ollama.com/library/llama3.2:3b", "IFEval 77.4; buen valor en 3B."),
    ModelInfo("llama3.2:1b", 1.0, 0.8,
              _c(general=0.45, writing=0.40, code=0.30, reasoning=0.10, multilingual=0.30),
              "https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct",
              "https://ollama.com/library/llama3.2:1b", "Rápido; clasificar/extraer/resumir."),

    # --- Phi (razonamiento alto por tamaño) ---
    ModelInfo("phi4:14b", 14.0, 8.7,
              _c(general=0.80, writing=0.72, code=0.66, reasoning=0.75, multilingual=0.55),
              "https://huggingface.co/microsoft/phi-4",
              "https://ollama.com/library/phi4", "Razonador fuerte 14B (no-thinking)."),
    ModelInfo("phi4-reasoning:14b", 14.0, 8.7,
              _c(general=0.78, writing=0.65, code=0.70, reasoning=0.99, multilingual=0.50),
              "https://huggingface.co/microsoft/Phi-4-reasoning-plus",
              "https://ollama.com/library/phi4-reasoning",
              "AIME-24 81%, GPQA 69%. Casi-frontier en razonamiento.", thinking=True),
    ModelInfo("phi4-mini:3.8b", 3.8, 2.8,
              _c(general=0.60, writing=0.55, code=0.66, reasoning=0.55, multilingual=0.45),
              "https://huggingface.co/microsoft/Phi-4-mini-instruct",
              "https://ollama.com/library/phi4-mini", "BCB-C 43 pese a 3.8B."),
    ModelInfo("phi3.5:3.8b", 3.8, 2.6,
              _c(general=0.57, writing=0.50, code=0.55, reasoning=0.45, multilingual=0.45),
              "https://huggingface.co/microsoft/Phi-3.5-mini-instruct",
              "https://ollama.com/library/phi3.5", "Repite en long-form; flojo en IFEval."),

    # --- DeepSeek-R1 distills (razonadores; thinking obligado) ---
    ModelInfo("deepseek-r1:14b", 14.0, 8.7,
              _c(general=0.63, writing=0.50, code=0.55, reasoning=0.85, multilingual=0.45),
              "https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
              "https://ollama.com/library/deepseek-r1:14b",
              "MATH-500 93.9, AIME-24 69.7.", thinking=True),
    ModelInfo("deepseek-r1:8b", 8.0, 5.0,
              _c(general=0.48, writing=0.40, code=0.50, reasoning=0.63, multilingual=0.40),
              "https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
              "https://ollama.com/library/deepseek-r1:8b", "MATH-500 89.1.", thinking=True),
    ModelInfo("deepseek-r1:7b", 7.0, 4.5,
              _c(general=0.50, writing=0.40, code=0.50, reasoning=0.68, multilingual=0.40),
              "https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
              "https://ollama.com/library/deepseek-r1:7b", "MATH-500 92.8.", thinking=True),
    ModelInfo("deepseek-r1:1.5b", 1.5, 1.2,
              _c(general=0.35, writing=0.25, code=0.30, reasoning=0.36, multilingual=0.25),
              "https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
              "https://ollama.com/library/deepseek-r1:1.5b",
              "MATH-500 83.9 pese a 1.5B; el único razonador en 8GB CPU.", thinking=True),

    # --- DeepSeek-Coder ---
    ModelInfo("deepseek-coder-v2:16b", 16.0, 9.5,
              _c(general=0.55, writing=0.45, code=0.71, reasoning=0.40, multilingual=0.45),
              "https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
              "https://ollama.com/library/deepseek-coder-v2:16b",
              "MoE 16B (2.4B activos): RAM de 16B, velocidad de ~3B."),
    ModelInfo("deepseek-coder:6.7b", 6.7, 4.4,
              _c(general=0.45, writing=0.40, code=0.62, reasoning=0.25, multilingual=0.35),
              "https://huggingface.co/deepseek-ai/deepseek-coder-6.7b-instruct",
              "https://ollama.com/library/deepseek-coder:6.7b"),

    # --- Multilingüe / español (traducción) ---
    ModelInfo("aya-expanse:8b", 8.0, 5.0,
              _c(general=0.55, writing=0.70, code=0.35, reasoning=0.30, multilingual=0.85),
              "https://huggingface.co/CohereLabs/aya-expanse-8b",
              "https://ollama.com/library/aya-expanse:8b",
              "23 idiomas; mejor para TRADUCCIÓN/redacción multilingüe (m-ArenaHard 76.6%)."),
    ModelInfo("mistral-nemo:12b", 12.0, 7.5,
              _c(general=0.65, writing=0.62, code=0.45, reasoning=0.30, multilingual=0.68),
              "https://huggingface.co/mistralai/Mistral-Nemo-Instruct-2407",
              "https://ollama.com/library/mistral-nemo:12b",
              "128K contexto; lenguas romances. Bueno para resumen largo en ES."),
    ModelInfo("mistral:7b", 7.0, 4.5,
              _c(general=0.52, writing=0.50, code=0.40, reasoning=0.20, multilingual=0.45),
              "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3",
              "https://ollama.com/library/mistral:7b", "Apache-2.0; ecosistema Mistral."),

    # --- Gemma ---
    ModelInfo("gemma2:9b", 9.0, 5.5,
              _c(general=0.75, writing=0.72, code=0.43, reasoning=0.10, multilingual=0.68),
              "https://huggingface.co/google/gemma-2-9b-it",
              "https://ollama.com/library/gemma2:9b", "Arena Elo 1187; fuerte multilingüe."),
    ModelInfo("gemma2:2b", 2.0, 1.7,
              _c(general=0.42, writing=0.40, code=0.40, reasoning=0.10, multilingual=0.40),
              "https://huggingface.co/google/gemma-2-2b-it",
              "https://ollama.com/library/gemma2:2b"),
]


def _params_in(name: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", name.lower())
    return float(m.group(1)) if m else None


def match(model_name: str) -> ModelInfo | None:
    """Empareja un tag de ollama (p.ej. 'qwen2.5-coder:7b-instruct-q4') con el catálogo."""
    n = model_name.lower()
    # 1) familia + tamaño exactos
    for e in CATALOG:
        fam, size = e.family.split(":")
        # Require the model name to start with "family:" to avoid false positives where
        # a shorter family name (e.g. "phi4") is a prefix of a longer one ("phi4-reasoning"),
        # or where a digit from the size string (e.g. "3" from "3b") accidentally matches
        # a digit that is part of the family version (e.g. the "3" in "llama3.2:1b").
        if n.startswith(fam + ":") and (
            n[len(fam) + 1:].startswith(size.replace("b", ""))
            or _params_in(n) == e.params_b
        ):
            return e
    # 2) sólo familia base (sin tamaño) — empareja la primera (mayor) de esa familia
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
    if axis == "general":
        return base
    if axis in ("writing", "multilingual"):
        return base * 0.92
    return base * 0.85  # code / reasoning: más exigentes para un desconocido


def axis_for_task(task_type: str, has_code: bool) -> str:
    """Compat: el mapeo canónico vive en task_policy.axis_for (que llama aquí)."""
    if has_code or task_type in ("loop_refine", "loop_verify", "code"):
        return "code"
    if task_type == "deep_reason":
        return "reasoning"
    if task_type == "write":
        return "writing"
    if task_type == "translate":
        return "multilingual"
    return "general"


def best_local_for(axis: str, available: list[str], max_params_b: float) -> str | None:
    """Mejor modelo DISPONIBLE que cabe en la máquina y es competente en el eje dado.
    Empareja capacidad alta con el menor tamaño a igualdad (más barato/rápido)."""
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


# ---------------------------------------------------------------------------
# Taxonomía de MÁQUINA: qué modelo es razonable por clase de hardware. Sirve de
# documentación y para que /v1/node sugiera modelos a instalar. El límite duro de
# "qué cabe" lo calcula profiler._max_params_q4; esto añade la recomendación por eje.
# Fuente: estudio de hardware (footprint Q4_K_M, KV-cache, tok/s) — docs/MODELS.md.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MachineTier:
    key: str
    label: str
    max_params_b: float       # mayor modelo práctico (interactivo) en Q4
    tok_s_range: str
    recommend: dict           # eje -> tag de modelo recomendado
    note: str = ""


MACHINE_TIERS: list[MachineTier] = [
    MachineTier("cpu_small", "≤8 GB RAM, sin GPU", 3.0, "5-10 t/s",
                {"general": "qwen3:4b", "writing": "qwen3:4b", "code": "qwen2.5-coder:3b",
                 "reasoning": "deepseek-r1:1.5b", "multilingual": "qwen2.5:3b"},
                "7B 'cabe' pero <5 t/s; mejor escalar a la nube en tareas duras."),
    MachineTier("cpu_large", "16-32 GB RAM, sin GPU (o Apple 16GB)", 7.0, "8-22 t/s",
                {"general": "qwen3:8b", "writing": "qwen3:8b", "code": "qwen2.5-coder:7b",
                 "reasoning": "deepseek-r1:7b", "multilingual": "aya-expanse:8b"},
                "7B-8B cómodos; Apple 16GB es la mejor opción portátil."),
    MachineTier("gpu_12gb", "GPU 8-12 GB VRAM (RTX 3060/4070)", 8.0, "25-52 t/s",
                {"general": "qwen3:8b", "writing": "qwen3:8b", "code": "qwen2.5-coder:7b",
                 "reasoning": "qwen3:8b", "multilingual": "aya-expanse:8b"},
                "14B sólo a contexto corto; KV-cache manda con contextos largos."),
    MachineTier("gpu_24gb", "GPU 24 GB+ o Apple 32-64 GB", 32.0, "35-135 t/s",
                {"general": "qwen2.5:14b", "writing": "qwen2.5:14b", "code": "qwen2.5-coder:32b",
                 "reasoning": "phi4-reasoning:14b", "multilingual": "qwen3:14b"},
                "14B con margen para contexto largo; 32B coder cabe en 24GB."),
]


def tier_for(ram_gb: float, gpu_vendor: str, vram_gb: float) -> MachineTier:
    """Clasifica la máquina en un MachineTier (recomendación por eje)."""
    if gpu_vendor in ("nvidia", "amd") and vram_gb >= 20:
        return MACHINE_TIERS[3]
    if gpu_vendor == "apple" and ram_gb >= 32:
        return MACHINE_TIERS[3]
    if gpu_vendor in ("nvidia", "amd") and vram_gb >= 8:
        return MACHINE_TIERS[2]
    if ram_gb >= 16 or (gpu_vendor == "apple" and ram_gb >= 16):
        return MACHINE_TIERS[1]
    return MACHINE_TIERS[0]


def tiers_as_table() -> list[dict]:
    return [
        {"tier": t.label, "max_params_b": t.max_params_b, "tok_s": t.tok_s_range,
         "code": t.recommend["code"], "writing": t.recommend["writing"],
         "reasoning": t.recommend["reasoning"], "multilingual": t.recommend["multilingual"],
         "note": t.note}
        for t in MACHINE_TIERS
    ]


# ---------------------------------------------------------------------------
# Catálogo de modelos ORQUESTADOS (tier de pago) — alcanzados vía un backend de
# agente (claude/codex/opencode/copilot) con la SUSCRIPCIÓN del usuario, NO con una
# API key de pago por token. Cada modelo tiene competencia por eje y un peso de coste
# relativo (0..1) que el router usa para preferir el más barato a igual competencia.
# El tier ("paid_cheap"/"paid_strong") sitúa el modelo en la escalera de coste.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OrchestratedModel:
    name: str
    tier: str             # "paid_cheap" | "paid_strong"
    caps: dict            # {eje: 0..1}
    cost_weight: float    # 0..1 relativo (no es $; pondera "consumo de cuota/seat")
    note: str = ""


def _oc(general, code, reasoning, writing=None, multilingual=None) -> dict:
    return {"general": general, "writing": writing or general,
            "code": code, "reasoning": reasoning,
            "multilingual": multilingual or general}


ORCHESTRATED: list[OrchestratedModel] = [
    OrchestratedModel("claude-opus-4-8", "paid_strong",
                      _oc(0.97, 0.95, 0.98, writing=0.97, multilingual=0.95), 1.00,
                      "Frontier reasoning/code."),
    OrchestratedModel("claude-sonnet-4-6", "paid_strong",
                      _oc(0.93, 0.92, 0.93, writing=0.94, multilingual=0.92), 0.55,
                      "Strong, cheaper than Opus."),
    OrchestratedModel("gpt-4o", "paid_strong",
                      _oc(0.95, 0.92, 0.94, writing=0.93, multilingual=0.93), 0.80),
    OrchestratedModel("claude-haiku-4-5-20251001", "paid_cheap",
                      _oc(0.85, 0.80, 0.80, writing=0.86, multilingual=0.84), 0.18,
                      "Fast, cheap, capable."),
    OrchestratedModel("gpt-4o-mini", "paid_cheap",
                      _oc(0.80, 0.76, 0.76, writing=0.80, multilingual=0.78), 0.10),
]

_ORCH_BY_NAME = {m.name: m for m in ORCHESTRATED}


def orchestrated(name: str) -> OrchestratedModel | None:
    if name in _ORCH_BY_NAME:
        return _ORCH_BY_NAME[name]
    n = name.lower()
    for m in ORCHESTRATED:
        head = m.name.split("-")[0]
        if head in n:
            return m
    return None


def orchestrated_capability(name: str, axis: str = "general") -> float:
    m = orchestrated(name)
    if m:
        return m.caps.get(axis, m.caps.get("general", 0.85))
    return 0.85 if axis == "general" else 0.82  # prior genérico para un modelo de pago


def orchestrated_cost(name: str) -> float:
    m = orchestrated(name)
    return m.cost_weight if m else 0.5


def orchestrated_tier(name: str) -> str:
    m = orchestrated(name)
    return m.tier if m else "paid_strong"


def best_orchestrated_for(axis: str, available: list[str], tier: str | None = None) -> str | None:
    """Mejor modelo orquestado DISPONIBLE para el eje (y, si se da, dentro del tier).
    Ordena por competencia en el eje; ante un EMPATE cercano (~0.02) prefiere el de
    menor coste de cuota. El trade-off coste entre tiers lo resuelve la utilidad del
    router (λ_cost), así que aquí no se vuelve a penalizar el coste salvo en empates."""
    pool = [m for m in available if (tier is None or orchestrated_tier(m) == tier)]
    if not pool:
        return None
    return max(pool, key=lambda m: (round(orchestrated_capability(m, axis) / 0.02),
                                    -orchestrated_cost(m)))
