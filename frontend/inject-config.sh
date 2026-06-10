#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════════
# EcoQuest — Runtime Config Injection Script for Frontend
# Substitutes the BACKEND_URL placeholder in app.js at container startup.
# ═══════════════════════════════════════════════════════════════════════════════
set -eu

TARGET_FILE="/usr/share/nginx/html/assets/js/app.js"
VAL="${BACKEND_URL:-http://localhost:8080}"

echo "[INFO] Injecting BACKEND_URL=${VAL} into ${TARGET_FILE}"

if [ -f "${TARGET_FILE}" ]; then
  # Use | as delimiter since URL contains slashes
  sed -i "s|BACKEND_URL_PLACEHOLDER|${VAL}|g" "${TARGET_FILE}"
  echo "[SUCCESS] Injected configuration."
else
  echo "[ERROR] Target file ${TARGET_FILE} not found!"
  exit 1
fi
