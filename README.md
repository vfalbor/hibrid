# hibrid 🔀

**El primer router que conoce TU máquina.**

Orquestador transparente que combina, sin que el usuario lo note, modelos LLM en la
nube (Claude Opus, Haiku, GPT…) con inferencia **local/on-premise**. Para cada petición
decide *dónde* ejecutarla según:

- **capacidades reales de la máquina** del usuario (RAM, VRAM, chip Apple, CPU),
- **modelos a los que tiene acceso** (locales detectados + claves de nube),
- **complejidad de la tarea**,
- **coste, latencia y privacidad**.

Expone una **API local OpenAI-compatible**: adoptar hibrid es *cambiar la URL*. En la
línea de `tokenstransfer` y `tokenstranslate`.

> Diseñado a partir de la investigación consolidada de un equipo de 3 agentes
> (literatura científica, benchmarks de inferencia local y análisis de mercado).
> Ver [`docs/INVESTIGACION.md`](docs/INVESTIGACION.md) y [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

---

## Por qué hibrid (el hueco)

| | Gateways cloud (OpenRouter, LiteLLM, Not Diamond…) | Apps locales (Ollama, LM Studio, Jan…) | **hibrid** |
|---|---|---|---|
| Routing automático por complejidad | ✅ | ❌ (manual) | ✅ |
| Mira el **hardware local** | ❌ | parcial (recomienda descarga) | ✅ **mide tok/s reales** |
| Local + nube **transparente y automático** | ❌ | ❌ (a mano) | ✅ |
| **Privacidad** como override duro (PII no sale) | ❌ | parcial | ✅ |

El cruce de esos ejes hoy **solo existe en papers** (Hybrid LLM, FrugalGPT, PRISM,
Minions). hibrid lo empaqueta como producto.

---

## Cómo decide (resumen)

1. **classify** — señales baratas de la petición: longitud, idioma, ¿código?, **PII**, complejidad 0–1.
2. **router.decide** — `d* = argmax U(d)` con
   `U(d) = calidad − λ_cost·coste − λ_lat·latencia − λ_priv·riesgo_privacidad`.
   Overrides duros antes del argmax: **PII → local**, `allow_cloud=false` → local, `force`.
3. **ejecuta** en el destino elegido (local OpenAI-compat / Anthropic / OpenAI).
4. **cascada** — si fue local y la **confianza calibrada** < umbral, **escala a la nube**
   (y el calibrador Platt aprende online).

El perfil de hardware + un **micro-benchmark de arranque** (tok/s reales por modelo)
se cachean por nodo: ningún competidor enruta por velocidad medida en *tu* máquina.

---

## Arranque

```bash
cd hibrid
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # añade tus claves y endpoints locales
bash run.sh                   # arranca en :8095
```

Requiere (opcional pero recomendado) un runtime local OpenAI-compatible corriendo:
`ollama serve` (11434), `llama-server` (8080) o LM Studio (1234).

## Uso (cliente OpenAI estándar)

```bash
curl http://localhost:8095/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "hibrid-auto",
  "messages": [{"role":"user","content":"Traduce \"hola mundo\" al inglés"}]
}'
```

La respuesta incluye un bloque `hibrid` con la decisión tomada (destino, candidatos,
utilidad, si escaló y por qué) — totalmente transparente; un cliente OpenAI normal lo ignora.

Perillas por petición:
```json
{ "model":"hibrid-auto", "messages":[...],
  "hibrid": { "lambda_priv": 5.0, "allow_cloud": false, "force": "local" } }
```

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/v1/chat/completions` | Inferencia con routing automático (OpenAI-compatible) |
| GET | `/v1/models` | Modelos disponibles (local + nube) |
| GET | `/v1/node` | Perfil de hardware + tok/s medidos (transparencia) |
| POST | `/v1/node/refresh` | Re-detecta hardware y re-ejecuta el micro-benchmark |
| GET | `/v1/metrics` | KPIs: % resuelto local, % escalado, coste nube, latencia media |
| GET | `/health` | Healthcheck |

## Tests

```bash
python3 tests/test_router.py     # 6/6 — decisión, PII, offline, force, cascada
```

---

## Estado y roadmap

**MVP funcional** (este scaffold): profiler multiplataforma, micro-benchmark, registry,
classifier, router por utilidad, cascada con calibración Platt online, API OpenAI-compat,
persistencia SQLite, tests del motor de decisión.

**Siguiente** (según los avisos del equipo):
- Router **kNN** sobre embeddings del histórico (LitAgent: kNN bate a routers aprendidos).
- Evaluación contra **RouterBench/RouterEval** → cifra publicable del KPI.
- Modo **co-generación** (speculative decoding: borrador local + verificación nube).
- Plantearse montar el transporte sobre **LiteLLM** y aportar solo la capa de decisión
  (no reinventar la fontanería).
- Calibración de confianza robusta (es el punto que más puede hundir el KPI).
