"""Classifier barato de la tarea (capa 1 del router, pre-ejecución).

Extrae señales baratas (LitAgent): longitud, idioma, ¿código?, PII, dominio, y una
estimación de complejidad 0..1. No usa LLM: es un forward casi gratis de reglas +
heurísticas. La complejidad alimenta E[calidad(d)] y el gate de privacidad fuerza local.
"""
from __future__ import annotations

import re

from .schemas import ChatMessage, TaskFeatures

# --- PII: patrones conservadores. Si hay match, se activa el override de privacidad. ---
_PII_PATTERNS = [
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),                       # email
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),                            # tarjeta/cuenta
    re.compile(r"\b\d{8}[A-Za-z]\b"),                                  # DNI español
    re.compile(r"\b[A-Z]{2}\d{2}[ ]?\d{4}[ ]?\d{4}[ ]?\d{2,}\b"),     # IBAN
    re.compile(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"),                 # SSN US
    re.compile(r"(?i)\b(password|contraseña|api[_-]?key|secret|token)\b\s*[:=]"),
]

_CODE_HINTS = re.compile(
    r"```|def |class |function |import |#include|SELECT |public static|=>|console\.log|"
    r"</?[a-z]+>|\bvar\b|\bconst\b|\blet\b|pip install|npm install"
)

# Términos que suben la complejidad (razonamiento / multipaso / dominios duros).
_HARD_HINTS = re.compile(
    r"(?i)\b(demuestra|prueba|deriva|optimiz|refactor|arquitectura|algoritm|"
    r"analiza|explica por qué|paso a paso|step by step|prove|theorem|complejidad|"
    r"diseña|estrategia|trade-?off|debug|race condition|concurren)"
)
_EASY_HINTS = re.compile(
    r"(?i)\b(traduce|translate|resume|resumen|clasifica|classify|extrae|formatea|"
    r"corrige ortografía|lista|define|qué hora|saluda|hola)\b"
)
# Señales de tarea iterativa / loop (refinar, QA repetido, test-fix-retest, agéntico).
_LOOP_HINTS = re.compile(
    r"(?i)\b(refactoriza iterativamente|refina|itera|loop|bucle|hasta que pase|"
    r"until.*(pass|green)|run the tests|ejecuta los tests|test-?fix|retry until|"
    r"keep improving|sigue mejorando|fix all|corrige todos|lint hasta|qa loop)\b"
)
_VERIFY_HINTS = re.compile(
    r"(?i)\b(verifica(ción)? final|revisión final|final review|haz una última|"
    r"comprueba que todo|sign[- ]?off|aprueba|valida el resultado final)\b"
)


def _infer_task_type(text: str, complexity: float, has_code: bool) -> str:
    if _VERIFY_HINTS.search(text):
        return "loop_verify"
    if _LOOP_HINTS.search(text):
        return "loop_refine"
    if _EASY_HINTS.search(text) and complexity < 0.25:
        return "simple"
    if complexity >= 0.6 or (has_code and _HARD_HINTS.search(text)):
        return "deep_reason"
    return "general"


def _detect_language(text: str) -> str:
    es = len(re.findall(r"(?i)\b(el|la|de|que|por|para|con|una|cómo|qué|está)\b", text))
    en = len(re.findall(r"(?i)\b(the|of|and|to|for|with|how|what|is|are)\b", text))
    return "es" if es >= en else "en"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def classify(messages: list[ChatMessage]) -> TaskFeatures:
    text = "\n".join(m.content for m in messages)
    n_chars = len(text)
    n_tokens = _estimate_tokens(text)

    has_code = bool(_CODE_HINTS.search(text))
    has_pii = any(p.search(text) for p in _PII_PATTERNS)
    lang = _detect_language(text)

    # Complejidad 0..1: combina longitud, señales duras/fáciles y código.
    score = 0.0
    score += min(0.35, n_tokens / 4000)                  # longitud (max 0.35)
    score += 0.30 if _HARD_HINTS.search(text) else 0.0
    score += 0.15 if has_code else 0.0
    score -= 0.25 if _EASY_HINTS.search(text) else 0.0
    score += 0.10 * max(0, text.count("?") - 1)          # multipregunta
    complexity = max(0.0, min(1.0, score))

    domain = "code" if has_code else ("sensitive" if has_pii else "general")
    task_type = _infer_task_type(text, complexity, has_code)

    return TaskFeatures(
        n_chars=n_chars,
        n_tokens_est=n_tokens,
        language=lang,
        has_code=has_code,
        has_pii=has_pii,
        complexity=round(complexity, 3),
        domain=domain,
        task_type=task_type,
    )
