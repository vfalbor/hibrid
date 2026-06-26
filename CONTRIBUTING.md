# Contribuir a hibrid

¡Gracias por querer mejorar **hibrid**! Hay tres formas de contribuir, de menos a más técnica.

## 1. Añade el benchmark de tu máquina 🖥️ (la más valiosa, ¡y la más fácil!)

hibrid enruta mejor cuando conoce la velocidad **real** de cada máquina. Comparte la tuya:

```bash
hibrid serve            # arranca y mide tu hardware
curl localhost:8095/v1/node   # copia el JSON resultante
```

Abre un issue con la plantilla **"Add my machine benchmark"** y pega ese JSON (no contiene
datos personales: solo hardware, modelos y tok/s). Tu aporte mejora los *priors* de todos
los usuarios con hardware parecido. Es el corazón de la comunidad.

## 2. Publica un perfil de ejecución (routing policy) 🔀

¿Has afinado un perfil para tu caso (p.ej. "loop_refine para Mac 16GB" o "coding para RTX
4090")? Compártelo. Ver `docs/EXECUTION_PROFILES.md`. Un PR que añade un perfil bien
documentado es bienvenido.

## 3. Código 🛠️

```bash
git clone <repo> && cd hibrid
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 tests/test_router.py        # debe salir 10/10 OK
```

- Mantén los **tests en verde** y añade tests para lo nuevo (el motor de decisión se prueba
  sin red).
- Estilo de commits: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`.
- Abre el PR contra `main`. La CI corre los tests automáticamente.

Busca issues etiquetados **`good first issue`** para empezar.

## Código de conducta

Este proyecto sigue el [Código de Conducta](CODE_OF_CONDUCT.md). Sé amable.
