#!/bin/bash
set -e

# Asset service run modes:
# - api (default)
# - document-worker
# - questions-worker

MODE="${MODE:-api}"

case "${MODE}" in
  api)
    echo "Starting API server..."
    exec python main.py api
    ;;
  setup)
    echo "Running setup tasks..."
    exec python scripts/setup.py
    ;;
  document-worker)
    echo "Starting document worker mode..."
    exec python -m src.workers.document_extraction_worker
    ;;
  questions-worker)
    echo "Starting questions worker mode..."
    exec python -m src.workers.questions_extraction_worker
    ;;
  audit-log-worker)
    echo "Starting audit log worker mode..."
    exec python -m src.workers.audit_log_worker
    ;;
  *)
    echo "Invalid MODE: ${MODE}. Allowed values: api, document-worker, questions-worker, audit-log-worker"
    exit 1
    ;;
esac
