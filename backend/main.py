"""hibrid — orquestador transparente local<->nube. API OpenAI-compatible.

Flujo de una petición:
  1. classify()           -> features baratas (complejidad, PII, idioma, código)
  2. router.decide()      -> argmax U(d) con overrides (privacidad, force, offline)
  3. ejecuta en el destino elegido
  4. CASCADA: si fue local y la confianza CALIBRADA < umbral y se permite nube,
     escala a cloud_strong (FrugalGPT/AutoMix) y actualiza el calibrador online.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import backends as backends_mod
from . import classifier, db, dialects, profiles, providers, router
from .confidence import PlattCalibrator, raw_confidence
from .config import settings
from .registry import NodeProfile, build_node_profile
from .schemas import (ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
                      Choice, Destination, HibridOptions, RouteDecision, Usage)

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    STATE["node"] = await build_node_profile(use_cache=True, benchmark=True)
    STATE["calibrator"] = PlattCalibrator.load(settings.cache_path + ".platt")
    n: NodeProfile = STATE["node"]
    print(f"[hibrid] máquina={n.hardware.machine_class} "
          f"max_local≈{n.hardware.max_local_params_b}B "
          f"local_default={n.local_default} tok_s={n.tok_s} "
          f"cloud={n.cloud_models}")
    yield
    STATE["calibrator"].save(settings.cache_path + ".platt")


app = FastAPI(title="hibrid", version="0.1.0", lifespan=lifespan)


_LANDING_FILE = Path(__file__).parent / "static" / "index.html"
_LANDING_FALLBACK = (
    "<!doctype html><meta charset='utf-8'><title>hibrid</title>"
    "<h1>hibrid</h1><p>The router that knows your machine. "
    "<a href='https://github.com/vfalbor/hibrid'>GitHub</a></p>"
)


@app.get("/", response_class=HTMLResponse)
async def landing():
    # Servido desde fichero estático: separa la presentación del código de la app
    # y permite actualizar la landing sin reiniciar el servicio.
    try:
        return _LANDING_FILE.read_text(encoding="utf-8")
    except OSError:
        return _LANDING_FALLBACK


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hibrid"}


@app.get("/v1/node")
async def node_info():
    """Perfil de hardware + modelos + tok/s medidos (transparencia)."""
    return STATE["node"].to_dict()


@app.post("/v1/node/refresh")
async def node_refresh():
    STATE["node"] = await build_node_profile(use_cache=False, benchmark=True)
    return STATE["node"].to_dict()


@app.get("/v1/models")
async def list_models():
    n: NodeProfile = STATE["node"]
    data = [{"id": "hibrid-auto", "object": "model", "owned_by": "hibrid"}]
    data += [{"id": m, "object": "model", "owned_by": "local"} for m in n.local_models]
    data += [{"id": m, "object": "model", "owned_by": "cloud"} for m in n.cloud_models]
    return {"object": "list", "data": data}


@app.get("/v1/metrics")
async def metrics():
    return db.metrics()


@app.get("/v1/policy")
async def policy():
    """La matriz explícita task_type -> (eje, escalera de tiers): qué LLM por tarea,
    más la taxonomía de máquina (qué modelo local por eje según el hardware)."""
    from . import models_catalog, task_policy
    hw = STATE["node"].hardware
    tier = models_catalog.tier_for(hw.ram_gb, hw.gpu_vendor, hw.vram_gb)
    return {
        "task_policy": task_policy.as_table(),
        "axes": list(task_policy.axes()),
        "machine_tiers": models_catalog.tiers_as_table(),
        "this_node": {"tier": tier.key, "label": tier.label,
                      "max_params_b": tier.max_params_b,
                      "recommend_by_axis": tier.recommend},
        "backends": [b for b in STATE["node"].to_dict()["backends"]],
    }


async def _run(dest: Destination, messages: list[dict], temperature: float,
               max_tokens: int | None) -> providers.GenerationResult:
    if dest.kind == "local":
        return await providers.generate_local(dest.endpoint, dest.model, messages,
                                              temperature, max_tokens)
    # Tier de pago: se ejecuta vía el backend de orquestación elegido (sin API key).
    node: NodeProfile = STATE["node"]
    backend = next((b for b in node.backends if b.id == dest.backend), None)
    if backend is None:
        backend = backends_mod.pick_backend(node.backends, dest.model)
    if backend is None:
        raise HTTPException(status_code=503,
                            detail=f"sin backend de orquestación para {dest.model}")
    return await backends_mod.run_backend(backend, dest.model, messages,
                                          temperature, max_tokens)


def _mark_backend_down(node: NodeProfile, backend_id: str | None) -> None:
    """Marca un backend de orquestación como no disponible y purga de cloud_models los
    modelos que ya no sirve ningún backend disponible, para no volver a enrutar ahí."""
    for b in node.backends:
        if backend_id and b.id == backend_id:
            b.available = False
    served = backends_mod.available_orchestrated_models(node.backends)
    node.cloud_models = [m for m in node.cloud_models if m in served]


async def _run_resilient(dest: Destination, node: NodeProfile, messages: list[dict],
                         temperature: float, max_tokens: int | None,
                         candidates: list[Destination]):
    """Ejecuta `dest`; si es de pago y su backend falla (CLI sin login, timeout, etc.),
    marca el backend caído y CAE a local — un backend roto nunca debe tumbar la petición.
    Devuelve (result, used_dest, note). Lanza HTTPException sólo si no queda nada."""
    try:
        return await _run(dest, messages, temperature, max_tokens), dest, ""
    except HTTPException:
        raise
    except Exception as e:
        if dest.kind == "local":
            raise HTTPException(status_code=502, detail=f"local inference failed: {e}")
        _mark_backend_down(node, dest.backend)
        note = (f" | backend {dest.backend or dest.tier} failed "
                f"({str(e)[:80]}) → fell back to local")
        local = next((c for c in candidates if c.kind == "local"), None)
        if local is not None:
            try:
                return await _run(local, messages, temperature, max_tokens), local, note
            except Exception as e2:
                raise HTTPException(status_code=502,
                                    detail=f"local fallback also failed: {e2}")
        raise HTTPException(status_code=503,
                            detail=f"backend {dest.backend} failed and no local fallback: {e}")


async def _route_and_run(messages: list[ChatMessage], opts, temperature: float,
                         max_tokens: int | None):
    """Núcleo común a todos los dialectos: clasifica, decide, ejecuta y aplica la
    cascada de escalado. Devuelve (result, decision, confidence, escalated, latency)."""
    node: NodeProfile = STATE["node"]
    cal: PlattCalibrator = STATE["calibrator"]

    feat = classifier.classify(messages)
    try:
        decision: RouteDecision = router.decide(node, feat, opts)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    raw_messages = [{"role": m.role, "content": m.content} for m in messages]
    allow_cloud = opts.allow_cloud if opts else True

    t0 = time.perf_counter()
    result, used, note = await _run_resilient(
        decision.chosen, node, raw_messages, temperature, max_tokens, decision.candidates)
    if used is not decision.chosen:           # hubo fallback: refleja el destino REAL
        decision.chosen = used
        decision.reason += note
    confidence = None
    escalated = False

    # CASCADA: el perfil de ejecución limita hasta dónde escala (un loop no salta
    # al modelo caro por iteración).
    if decision.chosen.kind == "local" and allow_cloud and not (opts and opts.force):
        prof = profiles.get_profile(
            (opts.profile or opts.task_type) if opts else None
        ) if (opts and (opts.profile or opts.task_type)) else profiles.get_profile(feat.task_type)
        raw = raw_confidence(result.logprob_avg, result.text)
        confidence = cal.calibrate(raw)
        if confidence < settings.escalation_confidence and node.cloud_models:
            allowed = ["local_free", "paid_cheap", "paid_strong"]
            cap = allowed.index(prof.escalate_to)
            target = None
            for kind in ("cloud_strong", "cloud_cheap"):
                cand = next((d for d in decision.candidates if d.kind == kind), None)
                if cand and allowed.index(cand.tier) <= cap:
                    target = cand
                    break
            if target:
                # Si el backend de escalado falla, NO tumbamos la petición: nos quedamos
                # con el resultado local ya obtenido.
                try:
                    result = await _run(target, raw_messages, temperature, max_tokens)
                    escalated = True
                    decision.escalated = True
                    decision.chosen = target
                    decision.reason += (f" | escalado a {target.tier} (conf {confidence:.2f}"
                                        f" < {settings.escalation_confidence}, tope perfil={prof.escalate_to})")
                    cal.update(raw, correct=False)
                except Exception as e:
                    _mark_backend_down(node, target.backend)
                    decision.reason += (f" | escalado a {target.tier} falló "
                                        f"({str(e)[:60]}); se mantiene local")
                    cal.update(raw, correct=True)
            else:
                cal.update(raw, correct=True)
        else:
            cal.update(raw, correct=True)

    total_latency = time.perf_counter() - t0
    decision.confidence = confidence
    db.log_route(feat, decision, escalated=escalated, confidence=confidence,
                 latency_s=total_latency, cost_usd=decision.chosen.est_cost_usd,
                 prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens)
    return result, decision, confidence, escalated


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest):
    """Dialecto OpenAI (aider, Copilot-like, Gemini en modo OpenAI)."""
    result, decision, _conf, _esc = await _route_and_run(
        req.messages, req.hibrid, req.temperature, req.max_tokens)
    return ChatCompletionResponse(
        id=f"hibrid-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=f"hibrid-auto>{decision.chosen.tier}/{decision.chosen.model}",
        choices=[Choice(message=ChatMessage(role="assistant", content=result.text))],
        usage=Usage(prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.prompt_tokens + result.completion_tokens),
        hibrid=decision,
    )


@app.post("/v1/messages")
async def anthropic_messages(req: Request):
    """Dialecto Anthropic Messages. Permite apuntar Claude Code a hibrid con
    ANTHROPIC_BASE_URL=https://hibrid.tokenstree.eu y enrutar Opus->Haiku->local
    de forma transparente, devolviendo la respuesta en formato Anthropic."""
    body = await req.json()
    messages = dialects.anthropic_to_messages(body)
    hopts = HibridOptions(**body["hibrid"]) if isinstance(body.get("hibrid"), dict) else None
    temperature = float(body.get("temperature", 0.7))
    max_tokens = body.get("max_tokens")
    result, decision, _conf, _esc = await _route_and_run(messages, hopts, temperature, max_tokens)
    return dialects.result_to_anthropic(
        msg_id=f"msg_hibrid_{uuid.uuid4().hex[:16]}",
        text=result.text,
        model=f"hibrid-auto>{decision.chosen.tier}/{decision.chosen.model}",
        input_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        hibrid_meta={"tier": decision.chosen.tier, "model": decision.chosen.model,
                     "escalated": decision.escalated, "reason": decision.reason},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)
