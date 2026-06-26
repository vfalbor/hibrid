"""Confianza calibrada para el gate de escalado (capa 2 del router, post-ejecución).

LitAgent: la confianza cruda (log-probs) está mal calibrada; hay que calibrarla
(isotónica/Platt). Aquí implementamos:
  - una señal de confianza cruda a partir del avg logprob (o heurística si no hay logprobs),
  - un calibrador Platt (sigmoide logística) entrenable online con el histórico real.
Si baja del umbral, el router escala local->nube.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass


def raw_confidence(logprob_avg: float | None, text: str) -> float:
    """Confianza cruda 0..1. Si hay logprob medio, exp(logprob); si no, heurística."""
    if logprob_avg is not None:
        # logprob medio por token -> probabilidad media por token.
        return max(0.0, min(1.0, math.exp(logprob_avg)))
    # Heurística de respaldo: respuestas muy cortas o con marcadores de duda bajan confianza.
    t = text.strip().lower()
    if not t:
        return 0.0
    doubt = any(k in t for k in (
        "no estoy seguro", "not sure", "no lo sé", "i don't know", "cannot", "no puedo",
        "as an ai", "podría estar equivocado", "might be wrong",
    ))
    base = 0.7
    if doubt:
        base -= 0.4
    if len(t) < 15:
        base -= 0.2
    return max(0.0, min(1.0, base))


@dataclass
class PlattCalibrator:
    """Calibrador logístico: p_cal = sigmoid(a * raw + b). Se ajusta online por SGD."""
    a: float = 4.0
    b: float = -2.0

    def calibrate(self, raw: float) -> float:
        z = self.a * raw + self.b
        return 1.0 / (1.0 + math.exp(-z))

    def update(self, raw: float, correct: bool, lr: float = 0.05) -> None:
        """Un paso de SGD con etiqueta `correct` (¿el resultado local fue bueno?)."""
        p = self.calibrate(raw)
        y = 1.0 if correct else 0.0
        grad = p - y
        self.a -= lr * grad * raw
        self.b -= lr * grad

    # --- persistencia ---
    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump({"a": self.a, "b": self.b}, f)

    @classmethod
    def load(cls, path: str) -> "PlattCalibrator":
        if os.path.exists(path):
            try:
                with open(path) as f:
                    d = json.load(f)
                return cls(a=d.get("a", 4.0), b=d.get("b", -2.0))
            except Exception:
                pass
        return cls()
