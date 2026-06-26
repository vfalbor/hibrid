# tu portátil ya pagó por una GPU. tus loops de IA la ignoran

*Asunto (email): deja de quemar tokens caros en bucles*
*Preview: el 95% de las llamadas de un loop de IA pueden correr gratis en tu máquina. casi nadie lo hace. acabamos de construir lo que lo arregla.*

---

Tienes un agente refinando código. Escribe, corre los tests, falla, corrige, vuelve a correr. Veinte vueltas. Cincuenta. Cada vuelta es una llamada a un modelo de pago.

Ninguna de esas vueltas necesitaba el mejor modelo del mundo. La mayoría las habría resuelto un modelo abierto corriendo en la máquina que tienes delante. Pero fueron todas a la nube, a tarifa premium, porque tu herramienta no sabía distinguir.

Eso es lo que hemos venido a arreglar. Se llama **hibrid**, es open source, y la idea es simple de decir y rara de encontrar: **un router que sabe qué tiene tu máquina y decide solo qué se ejecuta en local y qué se va a la nube. Sin que tengas que pensarlo.**

## el problema que nadie mira

El mercado se ha partido en dos.

Por un lado, los gateways de nube (OpenRouter, LiteLLM y compañía). Enrutan muy bien entre modelos de pago. Pero tu ordenador no existe para ellos: tu GPU, tus 32 GB de RAM, tu Mac con memoria unificada que aguanta un 70B… nada de eso entra en la ecuación.

Por otro, las apps locales (Ollama, LM Studio). Corren modelos en tu máquina de maravilla. Pero la decisión de cuándo usar local y cuándo la nube la tomas tú, a mano, modelo por modelo.

El cruce de las dos cosas —un router automático que mira tu hardware *y* tu acceso a modelos de pago y reparte el trabajo según la tarea— hasta ahora solo vivía en papers de investigación. No en algo que puedas instalar.

## qué hace hibrid

Tres decisiones, todas automáticas, todas transparentes:

**Sabe qué corre tu máquina, de verdad.** Al arrancar, hibrid detecta tu RAM, tu VRAM, tu chip, y lanza un micro-benchmark que mide la velocidad *real* en tokens por segundo de los modelos que tienes. No se fía de tablas de internet. Mide tu máquina. Que yo sepa, ningún otro router hace esto.

**Reparte según el tipo de tarea, no solo según la pregunta.** Aquí está la pieza que cambia las cuentas. Una tarea suelta y difícil puede merecer el modelo caro: la pagas una vez. Pero un *loop* —refinar código, QA iterativo— son decenas o cientos de llamadas. hibrid las manda **local primero** y se reserva el pago para el único momento en que aporta: la verificación final. El bucle corre gratis; la nota final la pone el modelo bueno. Una vez.

**Tu dato sensible no sale de tu máquina.** Si hibrid detecta información personal en lo que vas a enviar —un email, un DNI, una clave— fuerza la ejecución en local. No es una preferencia que puedas olvidarte de activar. Es la regla. Un gateway de nube no puede prometerte esto: tu texto ya viajó a un tercero antes de decidir nada.

Y todo esto hablando el mismo idioma que ya usas: una API compatible con OpenAI. Adoptar hibrid es cambiar la URL. Nada más.

## por qué esto es de la comunidad, no nuestro

hibrid mejora cuando sabe lo que rinde cada máquina. Y eso no lo sabemos nosotros: lo sabéis vosotros, cada uno con su hardware.

Por eso la pieza central es un registro colaborativo de benchmarks. Instalas hibrid, mide tu máquina, y —si quieres— compartes el resultado: solo hardware y velocidad, jamás tus prompts. A cambio, el siguiente que llegue con un portátil como el tuyo enruta bien desde el primer minuto, sin esperar a medir.

Tú aportas un dato que a ti no te cuesta nada y al de al lado le ahorra dinero. El de al lado hace lo mismo por ti. Eso es una comunidad, no una lista de usuarios.

El código es Apache-2.0. Los perfiles de routing se comparten y se mejoran entre todos. Si tienes una máquina rara, tu benchmark es justo lo que le falta al proyecto.

## cómo lo construimos (en una tarde, con un equipo de agentes)

Un detalle que cuenta algo del momento que vivimos. El diseño de hibrid no salió de una sola cabeza. Montamos un equipo de tres agentes de IA que trabajaron en paralelo: uno barrió la literatura científica de routing nube-local, otro mapeó qué modelos corren en qué hardware y a qué velocidad real, y un tercero comparó todo lo que ya existe en el mercado y cruzó sus hallazgos con los de los otros dos.

De ahí salió el diseño, y del diseño salió el código. Tres agentes investigando como un equipo, no como tres búsquedas sueltas. Es, además, la clase de trabajo —loops largos de investigación y refinado— para la que hibrid está pensado.

## pruébalo

```bash
pip install hibrid
hibrid serve
curl localhost:8095/v1/node   # mira qué dice de tu máquina
```

Apunta tu cliente de siempre a `localhost:8095` y deja que decida.

Si te ahorra una factura, devuélvelo: comparte el benchmark de tu máquina en el repo. Es la contribución más fácil y la más útil.

**El router que conoce tu máquina. Open source. Tuyo.**

→ *[repo en GitHub]* · *[documentación]* · *hibrid.tokenstree.eu*
