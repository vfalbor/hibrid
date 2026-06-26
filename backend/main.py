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

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from . import classifier, db, profiles, providers, router
from .confidence import PlattCalibrator, raw_confidence
from .config import settings
from .registry import NodeProfile, build_node_profile
from .schemas import (ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
                      Choice, Destination, RouteDecision, Usage)

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


_LANDING = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>hibrid — the router that knows your machine</title>
<style>
:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--ac:#3fb950;--card:#161b22;--bd:#30363d}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--fg);line-height:1.6} .wrap{max-width:780px;margin:0 auto;padding:64px 24px}
h1{font-size:40px;margin:0 0 8px;letter-spacing:-.02em} .tag{color:var(--ac);font-weight:600}
p{color:var(--fg)} .mut{color:var(--mut)} code,pre{font-family:ui-monospace,Menlo,Consolas,monospace}
pre{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:16px;overflow-x:auto;font-size:14px}
.grid{display:grid;gap:14px;grid-template-columns:1fr 1fr;margin:28px 0}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:16px}
.card b{color:var(--ac)} a{color:var(--ac)} .links a{margin-right:18px;font-weight:600}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<h1>hibrid</h1>
<p class="tag">The router that knows your machine.</p>
<p>Open-source, local-first router for LLM workloads. It detects what your hardware can run,
measures its real speed, and decides — automatically and transparently — what runs locally
and what goes to the cloud. Loops run free on your machine; your private data never leaves it.</p>
<div class="grid">
<div class="card"><b>Hardware-aware</b><br>Micro-benchmarks your machine's real tok/s and routes accordingly.</div>
<div class="card"><b>Task-type profiles</b><br>Loops go local-first; the expensive model is saved for the final check.</div>
<div class="card"><b>Privacy by default</b><br>Detected PII forces local execution — it's a rule, not a setting.</div>
<div class="card"><b>OpenAI-compatible</b><br>Adopting hibrid is changing the URL. Nothing else.</div>
</div>
<pre>pip install hibrid
hibrid serve
curl localhost:8095/v1/node   # what it says about your machine</pre>
<p class="links">
<a href="https://github.com/vfalbor/hibrid">GitHub</a>
<a href="https://tokenstree.eu/newsletter/2026-06-26-hibrid-router-that-knows-your-machine.html">Read the launch</a>
<a href="/v1/node">/v1/node</a>
<a href="/health">/health</a>
</p>
<p class="mut">Apache-2.0 · part of the tokenstree ecosystem · contribute your machine's benchmark on GitHub</p>
</div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return _LANDING


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


async def _run(dest: Destination, messages: list[dict], temperature: float,
               max_tokens: int | None) -> providers.GenerationResult:
    if dest.kind == "local":
        return await providers.generate_local(dest.endpoint, dest.model, messages,
                                              temperature, max_tokens)
    return await providers.generate_cloud(dest.kind, dest.model, messages,
                                          temperature, max_tokens)


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest):
    node: NodeProfile = STATE["node"]
    cal: PlattCalibrator = STATE["calibrator"]

    feat = classifier.classify(req.messages)
    try:
        decision: RouteDecision = router.decide(node, feat, req.hibrid)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    allow_cloud = req.hibrid.allow_cloud if req.hibrid else True

    # --- ejecución del destino elegido ---
    t0 = time.perf_counter()
    result = await _run(decision.chosen, messages, req.temperature, req.max_tokens)
    confidence = None
    escalated = False

    # --- CASCADA: verificación por confianza calibrada (sólo si fue local) ---
    # El perfil de ejecución limita HASTA dónde escala: un loop_refine no salta al
    # modelo caro por iteración (escalate_to=paid_cheap).
    if decision.chosen.kind == "local" and allow_cloud and not (req.hibrid and req.hibrid.force):
        prof = profiles.get_profile(
            (req.hibrid.profile or req.hibrid.task_type) if req.hibrid else None
        ) if (req.hibrid and (req.hibrid.profile or req.hibrid.task_type)) \
            else profiles.get_profile(feat.task_type)
        raw = raw_confidence(result.logprob_avg, result.text)
        confidence = cal.calibrate(raw)
        if confidence < settings.escalation_confidence and node.cloud_models:
            # Sólo se permite escalar a tiers <= escalate_to del perfil.
            allowed = ["local_free", "paid_cheap", "paid_strong"]
            cap = allowed.index(prof.escalate_to)
            target = None
            for kind in ("cloud_strong", "cloud_cheap"):
                cand = next((d for d in decision.candidates if d.kind == kind), None)
                if cand and allowed.index(cand.tier) <= cap:
                    target = cand
                    break
            if target:
                result = await _run(target, messages, req.temperature, req.max_tokens)
                escalated = True
                decision.escalated = True
                decision.chosen = target
                decision.reason += (f" | escalado a {target.tier} (conf {confidence:.2f}"
                                    f" < {settings.escalation_confidence}, tope perfil={prof.escalate_to})")
                cal.update(raw, correct=False)   # el local no bastó
        else:
            cal.update(raw, correct=True)        # el local sí bastó

    total_latency = time.perf_counter() - t0
    decision.confidence = confidence

    cost = decision.chosen.est_cost_usd
    db.log_route(feat, decision, escalated=escalated, confidence=confidence,
                 latency_s=total_latency, cost_usd=cost,
                 prompt_tokens=result.prompt_tokens,
                 completion_tokens=result.completion_tokens)

    return ChatCompletionResponse(
        id=f"hibrid-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=f"hibrid-auto>{decision.chosen.kind}/{decision.chosen.model}",
        choices=[Choice(message=ChatMessage(role="assistant", content=result.text))],
        usage=Usage(prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.prompt_tokens + result.completion_tokens),
        hibrid=decision,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)
