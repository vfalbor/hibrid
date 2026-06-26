# hibrid — Arquitectura

```
                          cliente (SDK OpenAI estándar)
                                     │  POST /v1/chat/completions
                                     ▼
        ┌─────────────────────────────────────────────────────────────┐
        │                       hibrid (FastAPI)                        │
        │                                                               │
        │  1) classifier.classify()  → features (complejidad, PII,      │
        │       idioma, código)  [barato, sin LLM]                      │
        │                                                               │
        │  2) router.decide()        → d* = argmax U(d)                 │
        │       U(d)=calidad − λc·coste − λl·latencia − λp·privacidad    │
        │       overrides: PII→local · allow_cloud=false→local · force   │
        │            usa: registry (modelos+coste+calidad)              │
        │                 profiler (hardware) + micro-benchmark (tok/s) │
        │                                                               │
        │  3) providers.run(d*)      → ejecuta en el destino            │
        │                                                               │
        │  4) CASCADA (si d*=local): confidence.calibrate()             │
        │       si < umbral → escala a cloud_strong (Platt aprende)     │
        │                                                               │
        │  5) db.log_route()  → histórico (kNN futuro + KPIs)           │
        └───────────┬───────────────────┬───────────────────┬──────────┘
                    ▼                   ▼                   ▼
          local (OpenAI-compat)   cloud_cheap          cloud_strong
          Ollama/llama.cpp/vLLM   Haiku / gpt-4o-mini  Opus / gpt-4o
          :11434/:8080/:1234      api.anthropic        api.anthropic
```

## Módulos

| Módulo | Responsabilidad | Origen de diseño |
|---|---|---|
| `profiler.py` | Detecta RAM/VRAM/CPU/chip y traduce a clase de máquina + mayor modelo Q4 ejecutable | BenchAgent |
| `registry.py` | Lista modelos locales (API) y de nube (claves); **micro-benchmark** de tok/s reales, cacheado | BenchAgent |
| `classifier.py` | Features baratas de la petición (longitud, idioma, código, **PII**, complejidad) | LitAgent (capa 1) |
| `router.py` | Función de utilidad `U(d)` + overrides duros → `argmax` | LitAgent (Hybrid LLM/RouteLLM) |
| `providers.py` | Cliente único: local OpenAI-compat + Anthropic + OpenAI | BenchAgent ("cambiar la URL") |
| `confidence.py` | Confianza cruda → **calibrador Platt** online (gate de escalado) | LitAgent (FrugalGPT/AutoMix; calibración) |
| `main.py` | API OpenAI-compat + orquestación + **cascada** de escalado | síntesis |
| `db.py` | SQLite: histórico para kNN y KPIs (% local, % escalado, coste) | LitAgent (RouterBench KPI) |

## Decisiones de diseño clave

- **Transparencia = API OpenAI-compatible local.** Mismo formato que Ollama/vLLM/LM Studio;
  no se inventa protocolo. Adopción "cambiando la URL".
- **Privacidad como override duro, no como peso blando**: si hay PII y `pii_forces_local`,
  el dato no sale aunque la utilidad de la nube fuese mayor. Es la cuña en sectores regulados.
- **El umbral de escalado se deriva** de la utilidad y de la confianza calibrada; no se
  codifica a mano. El calibrador Platt mejora solo con el uso.
- **Micro-benchmark real por nodo** en vez de cifras de blogs: alimenta `latencia(d)` con la
  velocidad medida en *esta* máquina. Es el foso competitivo.

## Riesgos vigilados (avisos del equipo)

1. **Calibración pobre** → escalado de más/menos; es lo que más afecta al KPI. Tests prioritarios.
2. **No reinventar la fontanería**: LiteLLM/Portkey/Cloudflare ya hacen fallbacks/retries/cost
   tracking; valorar montar el transporte encima y aportar solo la decisión.
3. **Ollama se acerca por abajo** (Cloud + Secure Minions). Diferenciarse en multi-proveedor y
   en la perilla privacidad/utilidad. Moverse rápido.
