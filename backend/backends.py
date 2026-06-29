"""Backends de orquestación: cómo hibrid alcanza el tier de PAGO sin API keys.

hibrid se sitúa POR DEBAJO de las herramientas de IA. Para la capacidad fuerte no usa
una clave de pago por token; delega "hacia abajo" en una capa ya autenticada. Tres
mecanismos tras una misma interfaz `Backend`, y un descubrimiento que decide cuáles
están disponibles para que el router elija EL MEJOR en cada momento (adaptativo):

  1. cli         -> ejecuta un agente headless con la SUSCRIPCIÓN del usuario:
                    `claude -p`, `codex exec`, `opencode run`, `copilot -p`.
  2. service     -> llama a un servicio local de "skills" que orquesta agentes debajo
                    (HIBRID_SKILLS_URL); el servicio posee la auth.
  3. passthrough -> reenvía al upstream reutilizando el token de sesión del propio
                    harness (p.ej. el OAuth de Claude Code que ya fluye), nunca una key.

El descubrimiento es barato y se cachea: comprueba qué CLIs están instalados y logueados,
qué servicio responde y si hay auth de passthrough. Cada backend declara qué modelos/tier
puede servir y una latencia/health medida. Si el preferido cae, el router usa el siguiente.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass

from .providers import GenerationResult, _approx_tokens

# --- Definición de los agentes CLI soportados -----------------------------------
# Cada entrada define: binario, cómo construir el comando para un prompt+modelo, y los
# modelos (lógicos) que sirve y a qué tier. Las plantillas usan {model}; el prompt va por
# stdin para no chocar con el quoting del shell.
# Algunos CLIs aceptan alias de modelo en lugar del id completo (p.ej. la CLI de Claude
# espera "haiku"/"sonnet"/"opus", no "claude-haiku-4-5-20251001"). Se mapea aquí.
MODEL_ALIASES: dict[str, str] = {
    "claude-opus-4-8": "opus",
    "claude-sonnet-4-6": "sonnet",
    "claude-haiku-4-5-20251001": "haiku",
}

# Texto que delata que el agente NO está autenticado / sin acceso aunque salga con código 0.
# Si aparece en la salida, el backend se considera caído (se reenruta / se descarta).
_ERROR_MARKERS = re.compile(
    r"(?i)(does not have access|please login|not logged in|log in to|unauthorized|"
    r"authentication|invalid api key|no api key|forbidden|quota|rate limit|"
    r"usage limit|credit balance|command not found)")


@dataclass(frozen=True)
class CliSpec:
    agent: str
    binary: str
    args: list[str]                 # plantilla; {model} se sustituye, prompt por stdin
    models: list[str]               # modelos orquestados que ofrece (ver models_catalog)
    aliased: bool = True            # ¿sustituir el id por su alias de MODEL_ALIASES?


CLI_SPECS: list[CliSpec] = [
    CliSpec("claude", "claude", ["-p", "--model", "{model}"],
            ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]),
    CliSpec("codex", "codex", ["exec", "--model", "{model}", "-"],
            ["gpt-4o", "gpt-4o-mini"], aliased=False),
    CliSpec("opencode", "opencode", ["run", "--model", "{model}"],
            ["claude-sonnet-4-6", "gpt-4o", "gpt-4o-mini"], aliased=False),
    CliSpec("copilot", "copilot", ["-p", "--model", "{model}"],
            ["gpt-4o", "gpt-4o-mini"], aliased=False),
]


def _model_arg(spec: CliSpec, model: str) -> str:
    return MODEL_ALIASES.get(model, model) if spec.aliased else model


@dataclass
class Backend:
    id: str                 # "cli:claude" | "service" | "passthrough"
    mechanism: str          # "cli" | "service" | "passthrough"
    agent: str              # claude|codex|opencode|copilot|"" (service/passthrough)
    models: list[str]       # modelos orquestados que puede servir
    available: bool
    latency_s: float = 2.0  # health/latencia medida (prior si no se midió)
    spec: CliSpec | None = None
    url: str | None = None

    def serves(self, model: str) -> bool:
        return model in self.models


# --------------------------- descubrimiento -------------------------------------

def _cli_available(spec: CliSpec) -> bool:
    """¿El agente está instalado Y operativo? No basta con que exista el binario: un CLI
    presente pero SIN login responde con un error de acceso (a veces con código 0) y haría
    fallar el routing. Por defecto se hace un health-prompt real y se descarta el backend si
    la salida delata falta de acceso. Desactivable con HIBRID_BACKEND_HEALTHCHECK=0 (sólo
    comprueba el binario; entonces la robustez recae en el fallback de ejecución)."""
    if not shutil.which(spec.binary):
        return False
    if os.getenv("HIBRID_BACKEND_HEALTHCHECK", "1") == "0":
        return True
    model = _model_arg(spec, spec.models[-1])  # el más barato (último de la lista)
    args = [a.replace("{model}", model) for a in spec.args]
    try:
        p = subprocess.run([spec.binary, *args], input=b"ping",
                           capture_output=True, timeout=45)
    except Exception:
        return False
    out = (p.stdout + p.stderr).decode(errors="replace")
    return p.returncode == 0 and not _ERROR_MARKERS.search(out) and bool(out.strip())


def discover_backends() -> list[Backend]:
    backends: list[Backend] = []
    # 1) Agentes CLI (suscripción del usuario)
    for spec in CLI_SPECS:
        backends.append(Backend(
            id=f"cli:{spec.agent}", mechanism="cli", agent=spec.agent,
            models=list(spec.models), available=_cli_available(spec),
            latency_s=2.5, spec=spec))
    # 2) Servicio de skills (orquestador externo)
    url = os.getenv("HIBRID_SKILLS_URL")
    if url:
        backends.append(Backend(
            id="service", mechanism="service", agent="",
            models=["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
                    "gpt-4o", "gpt-4o-mini"],
            available=True, latency_s=2.0, url=url.rstrip("/")))
    # 3) Passthrough con el token de sesión del harness
    if os.getenv("HIBRID_HARNESS_TOKEN") or os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        backends.append(Backend(
            id="passthrough", mechanism="passthrough", agent="",
            models=["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            available=True, latency_s=1.8))
    return backends


def available_orchestrated_models(backends: list[Backend]) -> list[str]:
    """Modelos orquestados servibles por AL MENOS un backend disponible."""
    seen: list[str] = []
    for b in backends:
        if not b.available:
            continue
        for m in b.models:
            if m not in seen:
                seen.append(m)
    return seen


def pick_backend(backends: list[Backend], model: str) -> Backend | None:
    """Backend disponible y de MENOR latencia que sirve el modelo (selección adaptativa)."""
    cands = [b for b in backends if b.available and b.serves(model)]
    if not cands:
        return None
    return min(cands, key=lambda b: b.latency_s)


# ------------------------------ ejecución ---------------------------------------

def _messages_to_prompt(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user").upper()
        parts.append(f"{role}: {m.get('content','')}")
    parts.append("ASSISTANT:")
    return "\n\n".join(parts)


async def run_backend(backend: Backend, model: str, messages: list[dict],
                      temperature: float, max_tokens: int | None) -> GenerationResult:
    if backend.mechanism == "cli":
        return await _run_cli(backend, model, messages)
    if backend.mechanism == "service":
        return await _run_service(backend, model, messages, temperature, max_tokens)
    if backend.mechanism == "passthrough":
        return await _run_passthrough(model, messages, temperature, max_tokens)
    raise RuntimeError(f"backend desconocido: {backend.mechanism}")


async def _run_cli(backend: Backend, model: str, messages: list[dict]) -> GenerationResult:
    assert backend.spec is not None
    args = [a.replace("{model}", _model_arg(backend.spec, model)) for a in backend.spec.args]
    prompt = _messages_to_prompt(messages)
    t0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        backend.spec.binary, *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(prompt.encode()), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"backend cli:{backend.agent} timeout")
    dt = time.perf_counter() - t0
    text = out.decode(errors="replace").strip()
    combined = text + "\n" + err.decode(errors="replace")
    # Algunos agentes (p.ej. claude sin login) imprimen el error en stdout con código 0.
    if proc.returncode != 0 or not text or _ERROR_MARKERS.search(combined):
        snippet = (combined.strip() or "sin salida")[:200]
        raise RuntimeError(f"backend cli:{backend.agent} error: {snippet}")
    return GenerationResult(text, _approx_tokens(prompt), _approx_tokens(text), dt)


async def _run_service(backend: Backend, model: str, messages: list[dict],
                       temperature: float, max_tokens: int | None) -> GenerationResult:
    import httpx
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(f"{backend.url}/v1/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
    dt = time.perf_counter() - t0
    choice = data["choices"][0]
    usage = data.get("usage", {})
    return GenerationResult(choice["message"]["content"], usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", _approx_tokens(choice["message"]["content"])), dt)


async def _run_passthrough(model: str, messages: list[dict],
                           temperature: float, max_tokens: int | None) -> GenerationResult:
    """Reenvía a Anthropic reutilizando el token de sesión del harness (Bearer OAuth),
    no una API key de pago por token."""
    import httpx
    token = os.getenv("HIBRID_HARNESS_TOKEN") or os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    sys = "\n".join(m["content"] for m in messages if m["role"] == "system")
    conv = [m for m in messages if m["role"] != "system"]
    payload = {"model": model, "max_tokens": max_tokens or 1024,
               "temperature": temperature, "messages": conv}
    if sys:
        payload["system"] = sys
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"authorization": f"Bearer {token}",
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload)
        r.raise_for_status()
        data = r.json()
    dt = time.perf_counter() - t0
    text = "".join(b.get("text", "") for b in data.get("content", []))
    usage = data.get("usage", {})
    return GenerationResult(text, usage.get("input_tokens", 0),
                            usage.get("output_tokens", _approx_tokens(text)), dt)
