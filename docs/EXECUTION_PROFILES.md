# hibrid — Perfiles de ejecución por tipo de tarea ("otra pensada")

## El cambio de enfoque

La primera versión del router decidía por **complejidad de la consulta suelta**. Pero el
coste real no depende solo de cuán difícil es *una* llamada, sino del **patrón de
ejecución de la tarea completa**. El caso que lo deja claro: los **loops**.

Un bucle de refinado de código o un QA iterativo hace **decenas o cientos de llamadas**.
Cada una es barata, pero el agregado es enorme. Si ese volumen va a tokens de pago, el
coste se dispara. Por eso un loop debe ir **local-first** y escalar con cuentagotas.

Conclusión: el **tipo de tarea** es una señal de routing de primera clase, por encima de
la complejidad puntual. hibrid lo modela con **perfiles de ejecución**.

## Tiers (mapeo libre/local ↔ pago)

| Tier | Qué es | Coste | Privacidad |
|---|---|---|---|
| `local_free` | open-weights en la máquina del usuario (Ollama/llama.cpp/vLLM) | ~0 | máxima |
| `paid_cheap` | modelos de pago de bajo coste (Haiku, gpt-4o-mini) | bajo | externa |
| `paid_strong` | modelos de pago top (Opus, gpt-4o) | alto | externa |
| `remote_local` *(futuro)* | otra máquina del usuario (home server) por red/SSH | ~0 | propia |

El **Registry** resuelve cada tier al modelo concreto disponible en *esta* máquina/cuenta.
Los perfiles hablan de tiers, no de modelos: así el mismo perfil funciona en cualquier hardware.

## Perfiles de fábrica

| Perfil | Orden de tiers | Escala hasta | Para qué |
|---|---|---|---|
| **loop_refine** | local_free → paid_cheap | **paid_cheap** (nunca caro por iteración) | refinar código, QA iterativo, test-fix-retest |
| **loop_verify** | paid_strong → paid_cheap → local_free | paid_strong | pase de verificación **final** único de un loop |
| **deep_reason** | paid_strong → local_free → paid_cheap | paid_strong | tarea compleja de 1 llamada (arquitectura, prueba, debug duro) |
| **simple** | local_free → paid_cheap | paid_cheap | clasificar, extraer, traducir, resumen corto |
| **interactive** | local_free → paid_cheap → paid_strong | paid_cheap | chat en vivo (λ_lat alto: la latencia pesa) |
| **batch** | local_free → paid_cheap | paid_cheap | procesado masivo sin urgencia (λ_lat=0: maximiza local) |
| **general** | local_free → paid_cheap → paid_strong | paid_strong | equilibrado (U(d) puro, sin sesgo) |

Cada perfil aporta: orden de tiers permitidos, un **bonus de utilidad por tier**
(subvenciona local en loops), overrides de las perillas λ, y el **tope de escalado** de la
cascada (`escalate_to`). El `loop_refine` da +0.6 de utilidad a `local_free` y excluye
`paid_strong`: aunque una iteración parezca compleja, **el bucle no salta al modelo caro**.

## Quién decide el perfil (transparencia total)

1. **Declarado por el skill/agente** (preferente). Un skill que es un loop de QA o de
   refinado **declara su perfil** en la petición:
   ```json
   { "model": "hibrid-auto", "messages": [...],
     "hibrid": { "task_type": "loop_refine" } }
   ```
   Esto es exactamente "los sistemas de ejecución definen su sistema preferido por tipo de
   tarea": el que mejor conoce que es un loop es el propio loop.
2. **Inferido por hibrid** si no se declara: el classifier detecta señales de loop
   ("itera", "hasta que pasen los tests", "fix all", "qa loop"...), de verificación final,
   de tarea simple o de razonamiento profundo, y elige el perfil.
3. **Forzado por el usuario** vía perillas (`force`, `allow_cloud`, λ) — máxima prioridad.

En todos los casos la respuesta devuelve el bloque `hibrid` con el perfil usado, el tier
elegido y si escaló y por qué. El usuario nunca tiene que elegir; pero **siempre puede ver**
la decisión. Esa es la transparencia exigida.

## Flujo completo de un loop (ejemplo)

```
Skill de refinado de código declara task_type=loop_refine
  iter 1..N:  hibrid -> local_free (modelo abierto en tu máquina)   [coste 0]
              si la confianza calibrada cae -> escala a paid_cheap   [tope del perfil]
              NUNCA a paid_strong dentro del bucle
  al terminar: el skill hace 1 llamada task_type=loop_verify
              hibrid -> paid_strong (Opus) para el visto bueno final  [1 sola vez]
```

Resultado: el 95–99% del volumen del loop corre gratis en local; el pago se reserva para
el único momento en que la calidad top aporta de verdad (la verificación final).

## Encaje con el ecosistema de skills/loops

- El comando `/loop`, ralph-loop y los skills de QA pueden **declarar su perfil** y, por
  defecto, beneficiarse de `loop_refine` sin configurar nada.
- Los perfiles son **datos contribuibles por la comunidad** (Policy Registry del hub):
  alguien publica "perfil loop_refine optimizado para Mac 16GB" o "perfil coding para RTX
  4090" y el resto lo descarga. Es una superficie de contribución concreta para la comunidad.

## Estado

Implementado y testeado (`tests/test_router.py`): inferencia de `task_type`, perfiles de
fábrica, filtro de tiers, subvención de local en loops, tope de escalado por perfil, y
declaración explícita por el skill. 10/10 tests en verde.
