"""Motor de decisión de hibrid (capa 1: predictivo, pre-ejecución).

Construye los destinos candidatos {local, cloud_cheap, cloud_strong}, estima
calidad/coste/latencia/privacidad de cada uno y elige d* = argmax U(d), donde

    U(d) = calidad(d) - lambda_cost*coste(d) - lambda_lat*latencia(d) - lambda_priv*riesgo_priv(d)

Reglas duras (overrides) antes del argmax:
  - PII + pii_forces_local -> sólo local (privacidad como compliance).
  - allow_cloud=False        -> sólo local.
  - force=...                -> destino fijo pedido por el cliente.
"""
from __future__ import annotations

from .config import settings
from .profiles import KIND_TO_TIER, ExecutionProfile, get_profile
from .registry import NodeProfile, cloud_cost, cloud_quality, local_quality, params_b
from .schemas import Destination, HibridOptions, RouteDecision, TaskFeatures

# Coste estimado de salida en tokens (para estimar $ por petición).
_EST_OUTPUT_TOKENS = 400


def _lambdas(opts: HibridOptions | None, prof: ExecutionProfile) -> tuple[float, float, float]:
    # Orden de precedencia: petición explícita > perfil de ejecución > settings.
    lc = settings.lambda_cost if prof.lambda_cost is None else prof.lambda_cost
    ll = settings.lambda_lat if prof.lambda_lat is None else prof.lambda_lat
    lp = settings.lambda_priv if prof.lambda_priv is None else prof.lambda_priv
    if opts:
        lc = opts.lambda_cost if opts.lambda_cost is not None else lc
        ll = opts.lambda_lat if opts.lambda_lat is not None else ll
        lp = opts.lambda_priv if opts.lambda_priv is not None else lp
    return lc, ll, lp


def _select_profile(feat: TaskFeatures, opts: HibridOptions | None) -> ExecutionProfile:
    # El skill/cliente puede declarar perfil o task_type; si no, se usa el inferido.
    if opts and opts.profile:
        return get_profile(opts.profile)
    if opts and opts.task_type:
        return get_profile(opts.task_type)
    return get_profile(feat.task_type)


def _local_destination(node: NodeProfile, feat: TaskFeatures) -> Destination | None:
    model = node.local_default or (node.local_models[0] if node.local_models else None)
    if not model or not node.local_endpoint:
        return None
    tps = node.tok_s.get(model, settings.min_local_tps)
    est_latency = _EST_OUTPUT_TOKENS / tps if tps > 0 else 999.0
    return Destination(
        kind="local",
        tier="local_free",
        model=model,
        endpoint=node.local_endpoint,
        est_quality=local_quality(model, feat.complexity),
        est_cost_usd=0.0,                 # local = sin coste de tokens
        est_latency_s=round(est_latency, 2),
        privacy_risk=0.0,                 # el dato no sale de la máquina
        tok_s=tps,
    )


def _cloud_destination(kind: str, model: str, feat: TaskFeatures) -> Destination:
    cost = cloud_cost(model) * (_EST_OUTPUT_TOKENS / 1_000_000)
    return Destination(
        kind=kind,
        tier=KIND_TO_TIER[kind],
        model=model,
        endpoint=None,
        est_quality=cloud_quality(model),
        est_cost_usd=round(cost, 6),
        est_latency_s=1.5 if kind == "cloud_cheap" else 3.0,  # prior; afinable
        privacy_risk=1.0,                 # sale a un tercero
        tok_s=0.0,
    )


def _utility(d: Destination, lc: float, ll: float, lp: float) -> float:
    return (
        d.est_quality
        - lc * d.est_cost_usd * 100      # escala el coste ($) a rango comparable
        - ll * (d.est_latency_s / 10)    # normaliza latencia
        - lp * d.privacy_risk
    )


def decide(node: NodeProfile, feat: TaskFeatures,
           opts: HibridOptions | None) -> RouteDecision:
    prof = _select_profile(feat, opts)
    lc, ll, lp = _lambdas(opts, prof)
    allow_cloud = opts.allow_cloud if opts else True

    # --- candidatos ---
    candidates: list[Destination] = []
    local = _local_destination(node, feat)
    if local:
        candidates.append(local)
    if allow_cloud and node.cloud_models:
        if settings.cloud_cheap_model in node.cloud_models:
            candidates.append(_cloud_destination("cloud_cheap", settings.cloud_cheap_model, feat))
        if settings.cloud_strong_model in node.cloud_models:
            candidates.append(_cloud_destination("cloud_strong", settings.cloud_strong_model, feat))

    if not candidates:
        raise RuntimeError("No hay destinos disponibles (ni local ni nube configurada).")

    # Utilidad base de todos (con bonus de tier del perfil).
    for d in candidates:
        d.utility = _utility(d, lc, ll, lp) + prof.tier_bonus.get(d.tier, 0.0)
        if d.kind == "local" and d.tok_s < settings.min_local_tps:
            d.utility -= 0.5  # local demasiado lento para tarea interactiva

    # --- overrides duros (preceden al perfil) ---
    forced_reason = ""
    if opts and opts.force:
        pool = [d for d in candidates if d.kind == opts.force] or candidates
        forced_reason = f"forzado por el cliente a {opts.force}"
    elif feat.has_pii and settings.pii_forces_local and local is not None:
        pool = [local]
        forced_reason = "override de privacidad: PII detectada -> sólo local"
    elif not allow_cloud and local is not None:
        pool = [local]
        forced_reason = "allow_cloud=False -> sólo local"
    else:
        # El perfil de ejecución restringe los tiers permitidos para este tipo de tarea.
        pool = [d for d in candidates if d.tier in prof.tier_order] or candidates

    chosen = max(pool, key=lambda d: d.utility)
    reason = forced_reason or (
        f"perfil={prof.name} (task_type={feat.task_type}) | "
        f"elegido {chosen.tier}:{chosen.kind}/{chosen.model} (U={chosen.utility:.3f})"
    )
    return RouteDecision(chosen=chosen, candidates=candidates, features=feat, reason=reason)
