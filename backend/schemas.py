"""Esquemas Pydantic: API OpenAI-compatible + estructuras internas de routing."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ----------------------- API OpenAI-compatible -----------------------

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "hibrid-auto"
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    # Extensiones hibrid: perillas por petición (sobreescriben las del .env).
    hibrid: Optional["HibridOptions"] = None


class HibridOptions(BaseModel):
    """Perillas que el cliente/skill puede ajustar por petición."""
    lambda_cost: Optional[float] = None
    lambda_lat: Optional[float] = None
    lambda_priv: Optional[float] = None
    force: Optional[Literal["local", "cloud_cheap", "cloud_strong"]] = None
    allow_cloud: bool = True  # si False, nunca sale a la nube (modo offline/privado)
    # Un skill o agente declara aquí su tipo de tarea / perfil de ejecución preferido.
    # p.ej. task_type="loop_refine" -> local-first, escala con cuentagotas.
    task_type: Optional[str] = None
    profile: Optional[str] = None  # nombre de perfil explícito (ver profiles.py)


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
    # Telemetría hibrid (transparente: el cliente puede ignorarla).
    hibrid: "RouteDecision"


# ----------------------- Estructuras internas -----------------------

class TaskFeatures(BaseModel):
    """Resultado del classifier barato."""
    n_chars: int
    n_tokens_est: int
    language: str
    has_code: bool
    has_pii: bool
    complexity: float = Field(ge=0.0, le=1.0)  # 0 trivial .. 1 muy difícil
    domain: str = "general"
    task_type: str = "general"  # general | simple | loop_refine | loop_verify | deep_reason | interactive | batch


class Destination(BaseModel):
    """Un destino candidato de ejecución."""
    kind: Literal["local", "cloud_cheap", "cloud_strong"]
    tier: str = ""  # local_free | paid_cheap | paid_strong (mapeo libre/pago)
    model: str
    endpoint: Optional[str] = None  # url OpenAI-compat (local) o None (cloud nativo)
    backend: Optional[str] = None   # backend de orquestación del tier de pago
                                    # (cli:claude | cli:codex | service | passthrough)
    # Estimaciones usadas por la función de utilidad.
    est_quality: float = 0.0       # 0..1
    est_cost_usd: float = 0.0      # coste estimado de la petición
    est_latency_s: float = 0.0     # latencia estimada
    privacy_risk: float = 0.0      # 0 (local) .. 1 (nube externa)
    tok_s: float = 0.0             # velocidad medida (micro-benchmark)
    utility: float = 0.0           # U(d) calculada


class RouteDecision(BaseModel):
    chosen: Destination
    candidates: list[Destination]
    features: TaskFeatures
    escalated: bool = False
    reason: str = ""
    confidence: Optional[float] = None


ChatCompletionRequest.model_rebuild()
ChatCompletionResponse.model_rebuild()
