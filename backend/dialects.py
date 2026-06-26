"""Traducción entre dialectos de API para que hibrid sea AI-agnóstico.

hibrid se sitúa POR DEBAJO de herramientas como Claude Code, Gemini CLI, aider o
Copilot: cada una habla su dialecto, apunta su base-URL a hibrid, y hibrid enruta
por debajo (Opus -> Haiku -> Qwen local) según el tipo de tarea, devolviendo la
respuesta en el dialecto que el cliente espera. Aquí viven las conversiones puras
(testeables sin red):

  - Anthropic Messages  (/v1/messages)        <- Claude Code (ANTHROPIC_BASE_URL)
  - OpenAI Chat         (/v1/chat/completions) <- aider, Copilot-like, Gemini (modo OpenAI)

El núcleo de decisión (classifier + router + cascada) es común; solo cambia la
gramática de entrada/salida.
"""
from __future__ import annotations

from typing import Any

from .schemas import ChatMessage


# ---------------- Anthropic Messages -> interno ----------------

def anthropic_to_messages(body: dict[str, Any]) -> list[ChatMessage]:
    msgs: list[ChatMessage] = []
    system = body.get("system")
    if system:
        if isinstance(system, list):  # bloques [{type:text,text:..}]
            system = "\n".join(b.get("text", "") for b in system if isinstance(b, dict))
        msgs.append(ChatMessage(role="system", content=str(system)))
    for m in body.get("messages", []):
        role = m.get("role", "user")
        content = m.get("content", "")
        msgs.append(ChatMessage(role=role, content=_flatten_content(content)))
    return msgs


def _flatten_content(content: Any) -> str:
    """Anthropic permite string o lista de bloques; aplanamos a texto."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "tool_result":
                    parts.append(_flatten_content(b.get("content", "")))
        return "\n".join(p for p in parts if p)
    return str(content or "")


# ---------------- interno -> Anthropic Messages ----------------

def result_to_anthropic(*, msg_id: str, text: str, model: str,
                        input_tokens: int, output_tokens: int,
                        hibrid_meta: dict | None = None) -> dict:
    out = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    if hibrid_meta is not None:
        out["hibrid"] = hibrid_meta  # telemetría: dónde se ejecutó realmente
    return out
