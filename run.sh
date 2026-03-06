#!/bin/sh
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "Error: ${VENV_PYTHON} not found or not executable."
  echo "Create the venv first: python3 -m venv venv"
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"

exec "${VENV_PYTHON}" -m uvicorn main:app --reload --host "${HOST}" --port "${PORT}"
