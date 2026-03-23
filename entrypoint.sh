#!/bin/bash
set -e

# Default to API mode, can be overridden with WORKER_MODE=true
if [ "${WORKER_MODE}" = "true" ]; then
    echo "Starting worker..."
    exec python -m src.worker
else
    echo "Starting API server..."
    exec python main.py
fi
