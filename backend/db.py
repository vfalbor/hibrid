"""Persistencia ligera (SQLite): histórico de decisiones para kNN online y métricas.

Cada fila registra la decisión y el resultado, base para:
  - afinar el calibrador de confianza (correct = ¿no hubo que escalar?),
  - el router kNN futuro (embedding de la query -> qué destino acertó),
  - el KPI "% resuelto local a paridad".
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    complexity REAL,
    language TEXT,
    has_code INTEGER,
    has_pii INTEGER,
    chosen_kind TEXT,
    chosen_model TEXT,
    escalated INTEGER,
    confidence REAL,
    latency_s REAL,
    cost_usd REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER
);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(settings.db_path)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)


def log_route(feat, decision, *, escalated: bool, confidence: float | None,
              latency_s: float, cost_usd: float,
              prompt_tokens: int, completion_tokens: int) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO routes (ts,complexity,language,has_code,has_pii,chosen_kind,"
            "chosen_model,escalated,confidence,latency_s,cost_usd,prompt_tokens,"
            "completion_tokens) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), feat.complexity, feat.language, int(feat.has_code),
             int(feat.has_pii), decision.chosen.kind, decision.chosen.model,
             int(escalated), confidence, latency_s, cost_usd,
             prompt_tokens, completion_tokens),
        )


def metrics() -> dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
        if not total:
            return {"total": 0}
        local = c.execute("SELECT COUNT(*) FROM routes WHERE chosen_kind='local'").fetchone()[0]
        escal = c.execute("SELECT COUNT(*) FROM routes WHERE escalated=1").fetchone()[0]
        cost = c.execute("SELECT COALESCE(SUM(cost_usd),0) FROM routes").fetchone()[0]
        avg_lat = c.execute("SELECT AVG(latency_s) FROM routes").fetchone()[0]
        return {
            "total": total,
            "pct_local": round(100 * local / total, 1),
            "pct_escalated": round(100 * escal / total, 1),
            "total_cloud_cost_usd": round(cost, 4),
            "avg_latency_s": round(avg_lat or 0, 3),
        }
