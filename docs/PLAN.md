# hibrid — Plan de trabajo, implementación y estrategia de comunidad

> Cómo pasar del scaffold actual a una **plataforma de comunidad** open-source,
> alojada en el servidor de tokenstree.eu bajo `hibrid.tokenstree.eu`, integrada
> de forma coherente en GitHub y con un motor de crecimiento de comunidad.

---

## 0. Idea en una frase

hibrid es una **herramienta local open-source** ("el router que conoce tu máquina")
+ un **servicio de comunidad** que agrega, de forma anónima y opt-in, las velocidades
reales (tok/s) que cada máquina obtiene con cada modelo. Esa base de datos colaborativa
mejora el routing de **todos** → efecto de red. Ese es el corazón de la comunidad.

**Por qué funciona como comunidad:** el valor que cada usuario aporta (su benchmark real)
beneficia a los demás, y a cambio recibe mejores recomendaciones de qué correr en su
hardware. Es el mismo patrón que los "Home GPU LLM Leaderboards", pero accionable desde
el propio router.

---

## 1. Las dos mitades del sistema

hibrid NO es un gateway central (la inferencia local corre en la máquina de cada usuario).
Por eso se separa en dos componentes con responsabilidades distintas:

### A) `hibrid-engine` (lo que corre en la máquina del usuario) — YA construido
El scaffold actual: FastAPI local, API OpenAI-compatible, profiler, micro-benchmark,
router por utilidad, cascada con calibración. Es el **producto open-source** que la gente
descarga y ejecuta. No requiere cuenta. Privacidad por defecto.

### B) `hibrid-hub` (lo que se aloja en `hibrid.tokenstree.eu`) — a construir
El **servicio de comunidad**. NO procesa prompts de nadie. Solo:
1. **Benchmark Registry / Leaderboard** — recibe envíos opt-in `(máquina, modelo, quant, tok/s)`
   y los agrega; sirve "priors" de velocidad para que un usuario nuevo enrute bien *antes*
   de su primer micro-benchmark.
2. **Policy Registry** — comparte presets de routing (perfiles de λ: "privacy-first",
   "low-cost", "low-latency", "coding") que la comunidad publica y descarga.
3. **Landing + Docs** — la cara pública, instalación en 1 línea, narrativa.
4. **Dashboard opcional** — para quien quiera telemetría agregada de su propio uso.

```
   Máquina del usuario                      hibrid.tokenstree.eu (comunidad)
   ┌──────────────────┐   opt-in submit     ┌─────────────────────────────┐
   │  hibrid-engine    │ ── (máquina,modelo, │  hibrid-hub                  │
   │  (OSS, local)     │     tok/s) ───────► │  • Benchmark Registry/Board  │
   │  prompts NUNCA    │ ◄── priors / policies│ • Policy Registry            │
   │  salen de aquí    │                     │  • Landing + Docs + Dashboard│
   └──────────────────┘                     └─────────────────────────────┘
```

Privacidad como principio fundacional: **los prompts y datos del usuario jamás llegan al
hub**; solo métricas de hardware/velocidad anónimas y *si el usuario lo activa*.

---

## 2. Partes principales del sistema (mapa de componentes)

| Componente | Dónde corre | Estado | Tecnología |
|---|---|---|---|
| Router + utilidad + cascada | engine (local) | ✅ hecho | FastAPI/Python |
| **Perfiles de ejecución por tipo de tarea** (loops local-first) | engine (local) | ✅ hecho | ver `EXECUTION_PROFILES.md` |
| Profiler hardware + micro-benchmark | engine (local) | ✅ hecho | psutil/pynvml/system_profiler |
| Providers local+nube (OpenAI-compat) | engine (local) | ✅ hecho | httpx |
| Calibración confianza (Platt online) | engine (local) | ✅ hecho | Python |
| Router **kNN** sobre histórico | engine (local) | ⬜ siguiente | embeddings + SQLite |
| Eval RouterBench/RouterEval | engine (CI) | ⬜ siguiente | dataset público |
| **Benchmark Registry + Leaderboard** | hub (.eu) | ⬜ a construir | FastAPI + Postgres |
| **Policy Registry** | hub (.eu) | ⬜ a construir | FastAPI + Postgres |
| **Landing + Docs + Dashboard web** | hub (.eu) | ⬜ a construir | React/Vite o Astro |
| Despliegue (Docker + nginx + certbot) | .eu server | ⬜ a construir | docker-compose |

---

## 3. Hosting en el servidor de tokenstree.eu (concreto, según su infra real)

Servidor: la máquina que sirve `tokenstree.eu` (IP en el inventario privado de infra, no
en este repo). Convención detectada: nginx en host con `sites-available/`, **certbot**
para certs, apps en **Docker Compose** proxiadas a `127.0.0.1:<puerto>` (como hnreviewer
→ :3000). Replicamos ese molde.

**Subdominio propuesto: `hibrid.tokenstree.eu`** (coherente con `androidwars.tokenstree.eu`,
`speaker.tokenstree.eu`).

Pasos de despliegue (mismo patrón que hnreviewer):
1. **DNS**: A record `hibrid.tokenstree.eu` → IP del servidor de tokenstree.eu.
2. **Repo en el server**: `git clone` en `/home/vfalbor/hibrid` (o `/opt/hibrid`).
3. **Docker Compose** del hub: contenedor `hibrid-hub` (FastAPI) en `127.0.0.1:8096`
   + `postgres` (registry). El **engine local NO se aloja aquí** — es lo que descarga el usuario.
4. **nginx vhost** `/etc/nginx/sites-available/hibrid` →
   `proxy_pass http://127.0.0.1:8096;` + `location /.well-known/acme-challenge/ { root /var/www/html; }`.
   `ln -s` a `sites-enabled/`.
5. **Certbot**: `certbot --nginx -d hibrid.tokenstree.eu` (renovación automática, ya configurada en la caja).
6. **CI/CD** (ver §4): un workflow que en cada release hace `ssh` + `docker compose pull && up -d`.

> Nota: el engine y el hub son **repos/imágenes distintos**. En `.eu` solo vive el **hub**.
> El engine se distribuye por PyPI/Docker Hub/`pip install hibrid` para correr en local.

---

## 4. Integración coherente con GitHub

Espejo de la estructura ya usada en hnreviewer (Dockerfile + docker-compose + CONTRIBUTING
+ LICENSE + README), elevada a estándar de proyecto de comunidad.

**Estructura de repos (recomendada): monorepo `hibrid`** con carpetas claras, para que
engine y hub evolucionen juntos y compartan esquemas:

```
hibrid/                      (github.com/<org>/hibrid)
├── engine/                  # el OSS local (lo ya construido)
├── hub/                     # backend de comunidad (FastAPI + Postgres)
├── web/                     # landing + docs + dashboard
├── docs/                    # investigación, arquitectura, este plan
├── .github/
│   ├── workflows/ci.yml     # tests del engine + lint en cada PR
│   ├── workflows/deploy.yml # despliegue a hibrid.tokenstree.eu en release
│   ├── ISSUE_TEMPLATE/      # bug / feature / "add my machine benchmark"
│   └── PULL_REQUEST_TEMPLATE.md
├── CONTRIBUTING.md · CODE_OF_CONDUCT.md · LICENSE (Apache-2.0) · SECURITY.md
└── README.md                # ✅ ya escrito
```

**Higiene GitHub que crea confianza y comunidad:**
- **Licencia permisiva** (Apache-2.0): clave para adopción y contribuciones.
- **CI verde visible**: badge de tests (ya hay `tests/test_router.py`, 6/6).
- **Releases semánticas** + changelog; el engine publicado en **PyPI** (`pip install hibrid`)
  y **Docker Hub** para arranque en 1 línea.
- **GitHub Discussions** activado (canal de comunidad sin fricción).
- **Issues etiquetados `good first issue`** — sobre todo: "añade el benchmark de tu máquina".
- **Plantilla de contribución de benchmark**: un PR o un issue estructurado que añade
  `(máquina, modelo, quant, tok/s)` al registry → convierte a usuarios en contribuyentes.
- **Org `tokenstree`** en GitHub que agrupe hibrid, tokenstransfer, tokenstranslate →
  presencia coherente de marca y descubrimiento cruzado.

---

## 5. Plan de trabajo por fases

### Fase 0 — Consolidar el engine (1 semana) · *casi hecho*
- [x] Scaffold engine + tests + docs de investigación/arquitectura.
- [ ] Empaquetar: `pyproject.toml`, publicar en PyPI y Docker Hub.
- [ ] `pip install hibrid && hibrid serve` funcionando en 1 línea.
- [ ] CI en GitHub Actions (tests + lint).

### Fase 1 — Calidad del router (2-3 semanas)
- [ ] Router **kNN** sobre histórico de la propia máquina (mejora con el uso).
- [ ] Evaluación contra **RouterBench/RouterEval** → cifra publicable del KPI
      ("% resuelto local a paridad"). Es el dato que da credibilidad técnica.
- [ ] Endurecer la **calibración de confianza** (el riesgo nº1 señalado por el equipo).
- [ ] (Opcional) modo **co-generación** (speculative decoding) detrás de un flag.

### Fase 2 — El hub de comunidad (3-4 semanas) · *aquí nace la plataforma*
- [ ] `hub/` FastAPI + Postgres: endpoints `POST /benchmarks`, `GET /benchmarks/leaderboard`,
      `GET /priors?machine=...`, `GET/POST /policies`.
- [ ] El engine: opt-in para **enviar** su micro-benchmark y **descargar** priors al arrancar.
- [ ] `web/` landing + leaderboard público + docs (Astro o React/Vite).
- [ ] Despliegue en `hibrid.tokenstree.eu` (Docker + nginx + certbot, §3).

### Fase 3 — Lanzamiento y comunidad (continuo)
- [ ] Lanzar en GitHub (público), Show HN, r/LocalLLaMA, Product Hunt.
- [ ] Leaderboard como gancho viral ("mira qué rinde tu Mac/RTX vs la media").
- [ ] Programa de contribución de benchmarks y de *routing policies*.
- [ ] Discord/Discussions; releases frecuentes; responder issues rápido.

---

## 6. Cómo se crea la comunidad (el flywheel)

1. **Gancho de entrada**: "instala hibrid y descubre qué LLM corre de verdad en TU máquina"
   → el micro-benchmark da un resultado personal e inmediato que la gente quiere compartir.
2. **Aporte que beneficia a todos**: ese benchmark alimenta el leaderboard y los priors →
   el siguiente usuario con el mismo hardware enruta bien desde el minuto cero.
3. **Estatus y comparación**: el leaderboard público ("tu M3 Max hace X tok/s, top 12%")
   es contenido compartible y competitivo — el motor de viralidad de los GPU leaderboards.
4. **Contribución profunda**: routing policies, nuevos backends locales, calibradores →
   contribuidores técnicos (vía `good first issue` y CONTRIBUTING claro).
5. **Coherencia de marca tokenstree**: enlazado desde tokenstree.eu y el resto del ecosistema;
   misma estética y narrativa de "herramientas de usuario, privacidad primero".

**Diferenciador defendible** (confirmado por el equipo de investigación): nadie más enruta
por velocidad **medida** en la máquina del usuario, ni ofrece privacidad como override duro.
La comunidad de benchmarks reales es además un **foso de datos** que un gateway cloud no puede
replicar.

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Calibración de confianza pobre → escala mal | Tests y eval dedicados (Fase 1); es la prioridad técnica |
| Ollama añade routing automático y nos invade | Multi-proveedor + perilla privacidad/utilidad + comunidad de datos; moverse rápido |
| Reinventar fontanería (gateways ya la tienen) | Montar transporte sobre LiteLLM si conviene; centrarse en la *capa de decisión* |
| Privacidad: que los benchmarks filtren datos | Solo métricas de hardware/velocidad, anónimas y opt-in; nunca prompts |
| Comunidad que no arranca | Gancho del leaderboard + 1-línea de instalación + `good first issue` de benchmarks |
