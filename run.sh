#!/usr/bin/env bash
# Arranque de hibrid (igual estilo que tokenstransfer/tokenstranslate).
set -e
cd "$(dirname "$0")"
[ -f .env ] && export $(grep -v '^#' .env | xargs) || true
python3 -m uvicorn backend.main:app --host "${HIBRID_HOST:-0.0.0.0}" --port "${HIBRID_PORT:-8095}"
