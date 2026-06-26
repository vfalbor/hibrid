"""Clientes de inferencia: local (OpenAI-compatible) y nube (Anthropic / OpenAI).

Idea central (BenchAgent): Ollama, llama.cpp y vLLM exponen todos la misma API
OpenAI-compatible, así que alternar local<->nube es cambiar la URL. La nube de
Anthropic usa su SDK nativo; OpenAI y locales comparten el formato /v1/chat/completions.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

from .config import settings


class GenerationResult:
    def __init__(self, text: str, prompt_tokens: int, completion_tokens: int,
                 latency_s: float, logprob_avg: Optional[float] = None):
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.latency_s = latency_s
        self.logprob_avg = logprob_avg  # señal de confianza si el backend la da

    @property
    def tok_s(self) -> float:
        return self.completion_tokens / self.latency_s if self.latency_s > 0 else 0.0


# ---------------- LOCAL (OpenAI-compatible) ----------------

async def list_local_models() -> tuple[Optional[str], list[str]]:
    """Devuelve (endpoint_activo, [modelos]) del primer runtime local que responda."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        for ep in settings.local_endpoints:
            try:
                r = await client.get(f"{ep}/models")
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    models = [m.get("id") for m in data if m.get("id")]
                    if models:
                        return ep, models
            except Exception:
                continue
    return None, []


async def generate_local(endpoint: str, model: str, messages: list[dict],
                         temperature: float, max_tokens: Optional[int]) -> GenerationResult:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "logprobs": True,  # para confianza; los backends que no lo soporten lo ignoran
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(f"{endpoint}/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
    dt = time.perf_counter() - t0
    choice = data["choices"][0]
    text = choice["message"]["content"]
    usage = data.get("usage", {})
    logprob = _extract_logprob(choice)
    return GenerationResult(
        text=text,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", _approx_tokens(text)),
        latency_s=dt,
        logprob_avg=logprob,
    )


def _extract_logprob(choice: dict) -> Optional[float]:
    try:
        contents = choice["logprobs"]["content"]
        vals = [c["logprob"] for c in contents if "logprob" in c]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


# ---------------- NUBE ----------------

async def generate_cloud(kind: str, model: str, messages: list[dict],
                         temperature: float, max_tokens: Optional[int]) -> GenerationResult:
    if model.startswith("claude") and settings.anthropic_api_key:
        return await _generate_anthropic(model, messages, temperature, max_tokens)
    if settings.openai_api_key:
        return await _generate_openai(model, messages, temperature, max_tokens)
    raise RuntimeError("No hay clave de nube configurada para el destino solicitado.")


async def _generate_anthropic(model, messages, temperature, max_tokens) -> GenerationResult:
    sys = "\n".join(m["content"] for m in messages if m["role"] == "system")
    conv = [m for m in messages if m["role"] != "system"]
    payload = {
        "model": model,
        "max_tokens": max_tokens or 1024,
        "temperature": temperature,
        "messages": conv,
    }
    if sys:
        payload["system"] = sys
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
    dt = time.perf_counter() - t0
    text = "".join(b.get("text", "") for b in data.get("content", []))
    usage = data.get("usage", {})
    return GenerationResult(text, usage.get("input_tokens", 0),
                            usage.get("output_tokens", _approx_tokens(text)), dt)


async def _generate_openai(model, messages, temperature, max_tokens) -> GenerationResult:
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
    dt = time.perf_counter() - t0
    choice = data["choices"][0]
    usage = data.get("usage", {})
    return GenerationResult(choice["message"]["content"], usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0), dt)


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)
