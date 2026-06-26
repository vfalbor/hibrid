# hibrid — Síntesis de investigación (equipo de 3 agentes)

Documento consolidado de los informes de **LitAgent** (literatura científica),
**BenchAgent** (capacidades de inferencia local) y **CompareAgent** (mercado).
Es la base de diseño de `hibrid`.

---

## 1. Qué es hibrid

Un **router/orquestador transparente** que combina, sin que el usuario lo note,
modelos LLM en la nube (Claude Opus, Haiku, GPT…) con inferencia local/on-premise.
Para cada petición decide *dónde* ejecutarla según:

- **(a) capacidades de la máquina** del usuario (RAM, VRAM, chip Apple, CPU),
- **(b) modelos a los que el usuario tiene acceso** (locales cargados + claves de nube),
- **(c) complejidad/tipo de la tarea**,
- **(d) coste, latencia y privacidad**.

Expone una **API local OpenAI-compatible** (`/v1/chat/completions`), igual que
tokenstransfer/tokenstranslate, de modo que adoptar hibrid es "cambiar la URL".

---

## 2. Hallazgos clave (literatura — LitAgent)

- **Patrón base**: *Hybrid LLM* (Ding et al., ICLR 2024) + *RouteLLM* (LMSYS 2024).
  Un clasificador ligero predice si el modelo local igualará a la nube, con una
  **"perilla de calidad" ajustable** en runtime → la mapeamos a coste/privacidad por usuario.
- **Arquitectura en 2 capas**:
  1. **Router predictivo** (antes de ejecutar) — decide local vs nube en 1 forward barato.
  2. **Cascada de verificación** (después de ejecutar en local) — si la **confianza
     calibrada** del resultado es baja, **escala a la nube** (FrugalGPT, AutoMix, Tabi).
- **La confianza cruda está mal calibrada** → calibrar con isotónica/Platt. Es el punto
  técnico que más puede hundir el KPI.
- **Señales de decisión** (de barata a cara): features de la query (longitud, idioma,
  ¿código?, PII) → embedding + **kNN** sobre histórico (kNN bate a routers aprendidos,
  2025) → confianza calibrada del modelo local.
- **Función de utilidad unificada**:
  `U(d) = E[calidad(d)] − λ_cost·coste(d) − λ_lat·latencia(d) − λ_priv·riesgo_priv(d)`,
  con `d* = argmax U(d)`. Los `λ` son las perillas por usuario; el umbral de escalado se
  **deriva**, no se fija a mano.
- **Co-generación**: speculative decoding (borrador local + verificación nube) = salida
  idéntica a la nube, 2-3× más rápido.
- **Evaluación**: RouterBench / RouterEval. KPI principal: **% de consultas resueltas
  localmente a paridad de calidad** (Hybrid LLM reporta 40%).

Refs: arxiv 2404.14618, 2406.18665, 2305.05176, 2310.12963, 2211.17192, 2403.12031.

---

## 3. Hallazgos clave (local — BenchAgent)

- **Runtimes**: Ollama (default laptop/desktop), llama.cpp (edge/CPU/AMD/Intel),
  vLLM (servidor GPU, 16-44× throughput). **Todos exponen API OpenAI-compatible** →
  alternar local↔nube es cambiar la URL del endpoint.
- **Cuantización ref**: `Q4_K_M` (<2% pérdida). Regla de memoria:
  `GB ≈ params_B × 0.65 (Q4) + 1-2 GB KV-cache`.
- **Mapa máquina → modelo** (orden de magnitud):

  | Clase | Modelos | tok/s | Tareas |
  |---|---|---|---|
  | 8 GB RAM CPU | 1-4B Q4 (Phi-4-mini, Llama 3.2 3B) | 8-15 | clasificar, extraer, resumen corto |
  | 16 GB RAM CPU | 7-8B Q4 | 7-12 | resumen, RAG, código simple |
  | 8 GB VRAM | 7-8B Q4 | 40-60 | chat, RAG, código |
  | 12-16 GB VRAM | 13-14B Q4 | 22-30 | razonamiento medio, agentes |
  | 24 GB VRAM (3090/4090) | 14-34B Q4 | 28-78 | razonamiento fuerte, código complejo |
  | Apple Silicon 64 GB+ | 70B Q4 | 8-13 | calidad alta (ventaja única) |
  | Servidor 48 GB+ | 70B Q4 con vLLM | alta concurrencia | producción |

- **Detección de capacidades** multiplataforma: `psutil` (RAM/CPU) +
  `pynvml`/`nvidia-smi`/`torch.cuda` (VRAM NVIDIA) + `system_profiler` (Apple).
- **Joya de diseño**: en vez de fiarse de cifras de blogs, hibrid corre un
  **micro-benchmark de arranque** que mide tok/s reales por `(máquina, modelo, quant)`
  y los cachea. Eso alimenta directamente `latencia(d)` de la función de utilidad.

---

## 4. Hallazgos clave (mercado — CompareAgent)

El mercado está partido y **el hueco de hibrid es el cruce**:

- **Routers/gateways cloud** (OpenRouter, Not Diamond, Martian, Unify, RouteLLM, LiteLLM,
  Cloudflare AI Gateway, Portkey): routing inteligente entre modelos *de nube*, pero
  **ninguno mira el hardware local**. "Local" es como mucho otro endpoint que declaras a mano.
- **Apps locales** (Ollama, LM Studio, Jan, GPT4All, LocalAI, Cline, Continue): ejecutan
  local muy bien, algunas detectan hardware para *recomendar descarga*, pero el routing
  local↔nube es **manual**.
- Lo que hace ambas cosas **solo existe en papers** (PRISM, IslandRun, Minions).

**Diferenciadores defendibles de hibrid:**
1. **Hardware-aware routing real** con micro-benchmark de tok/s medidos (nadie lo hace).
2. **Perilla unificada → función de utilidad** que incluye **privacidad** (los cloud routers no).
3. **Privacidad como override duro**: PII/salud/finanzas → fuerza local; el dato no sale.
4. **Transparencia tipo Ollama** pero con **decisión automática** (Ollama el `:cloud` lo pones tú).
5. **Cascada por confianza calibrada** + co-generación speculative.

**Avisos del equipo (riesgos):**
- No reinventar la "fontanería": hibrid puede montarse **encima de LiteLLM** como capa de
  transporte y aportar solo la **capa de decisión**.
- **Reutilizar RouteLLM** (OSS) y sustituir su "modelo débil fijo" por "el mayor modelo
  que ESTA máquina ejecuta a X tok/s".
- **Ollama se acerca por abajo** (Cloud + Secure Minions). Diferenciarse en multi-proveedor
  y en la perilla privacidad/utilidad. Moverse rápido.
- **Invertir en calibración de confianza**: si es pobre, se escala de más (se pierde coste) o
  de menos (se pierde calidad).

Narrativa de posicionamiento: **"el primer router que conoce TU máquina"**.

---

## 5. Decisión de arranque (MVP)

1. **Profiler** de hardware multiplataforma + **micro-benchmark** cacheado por nodo.
2. **Registry** de modelos disponibles (locales detectados vía API OpenAI-compat + nube por claves).
3. **Classifier** barato de la tarea: longitud, idioma, ¿código?, **PII** (privacy gate), dominio.
4. **Router** = función de utilidad `U(d)` con λ por usuario; `argmax`.
5. **Cascada**: ejecutar local → medir confianza calibrada → escalar a nube si baja.
6. **Providers**: cliente HTTP único contra endpoints OpenAI-compatible (local) + Anthropic/OpenAI (nube).
7. **DB** SQLite con histórico `(query → destino → resultado → coste/latencia)` para el kNN online.
8. **Eval** contra RouterBench/RouterEval. KPI: % resuelto local a paridad.
