"""Configuración central de hibrid.

Carga ajustes desde variables de entorno (.env). Los pesos lambda de la función
de utilidad son las "perillas" por defecto; cada petición puede sobreescribirlas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # --- API ---
    host: str = os.getenv("HIBRID_HOST", "0.0.0.0")
    port: int = int(os.getenv("HIBRID_PORT", "8095"))

    # --- Endpoints de inferencia local (OpenAI-compatibles) ---
    # Se prueban en orden; el primero que responda se usa como runtime local.
    local_endpoints: list[str] = field(default_factory=lambda: [
        e.strip() for e in os.getenv(
            "HIBRID_LOCAL_ENDPOINTS",
            "http://localhost:11434/v1,http://localhost:8080/v1,http://localhost:1234/v1",
        ).split(",") if e.strip()
    ])

    # --- Claves de nube (definen a qué modelos remotos tiene acceso el usuario) ---
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    # Modelos de nube preferidos (barato y potente). Mapean a "nube_barata"/"nube_potente".
    cloud_cheap_model: str = os.getenv("HIBRID_CLOUD_CHEAP", "claude-haiku-4-5-20251001")
    cloud_strong_model: str = os.getenv("HIBRID_CLOUD_STRONG", "claude-opus-4-8")

    # --- Pesos por defecto de la función de utilidad U(d) ---
    # U(d) = calidad - lambda_cost*coste - lambda_lat*latencia - lambda_priv*riesgo_priv
    lambda_cost: float = _f("HIBRID_LAMBDA_COST", 1.0)
    lambda_lat: float = _f("HIBRID_LAMBDA_LAT", 0.3)
    lambda_priv: float = _f("HIBRID_LAMBDA_PRIV", 2.0)

    # Umbral de confianza calibrada bajo el cual se escala local->nube.
    escalation_confidence: float = _f("HIBRID_ESCALATION_CONF", 0.55)

    # Velocidad mínima aceptable (tok/s) para usar local en tareas interactivas.
    min_local_tps: float = _f("HIBRID_MIN_LOCAL_TPS", 8.0)

    # --- Persistencia ---
    db_path: str = os.getenv("HIBRID_DB", os.path.join(os.path.dirname(__file__), "hibrid.db"))

    # Cache del perfil de hardware + micro-benchmark (evita re-medir en cada arranque).
    cache_path: str = os.getenv(
        "HIBRID_CACHE", os.path.join(os.path.dirname(__file__), "node_profile.json")
    )

    # Forzar local siempre que haya PII (override duro de privacidad).
    pii_forces_local: bool = os.getenv("HIBRID_PII_LOCAL", "true").lower() == "true"


settings = Settings()
