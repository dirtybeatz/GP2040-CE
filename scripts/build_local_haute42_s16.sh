#!/usr/bin/env bash
# Lokaler All-in-One Build für Haute42 S16 (Linux / WSL2 / macOS)
# Voraussetzung: PICO_SDK_PATH gesetzt, arm-none-eabi-gcc, cmake, ninja, node/npm, python3 (+ protobuf)

set -euo pipefail

BOARD_CONFIG="${1:-Haute42COSMOX}"
MACRO_SLOTS="${2:-10}"
MACRO_INPUTS="${3:-25}"

if [ -z "${PICO_SDK_PATH:-}" ]; then
  echo "[ERR] Bitte zuerst PICO_SDK_PATH exportieren (z.B. export PICO_SDK_PATH=$HOME/pico-sdk)."
  exit 1
fi

echo "=== 1/4: Patch anwenden (${MACRO_SLOTS} Slots x ${MACRO_INPUTS} Inputs) ==="
python3 scripts/patch_haute42_s16_10macros.py --slots "${MACRO_SLOTS}" --inputs "${MACRO_INPUTS}" --repo .

echo "=== 2/4: Web-Configurator bauen (www/) ==="
(cd www && npm ci && npm run build)

echo "=== 3/4: Firmware für ${BOARD_CONFIG} kompilieren ==="
rm -rf build
cmake -B build -G Ninja \
  -DPICO_BOARD=pico \
  -DPICO_PLATFORM=rp2040 \
  -DGP2040_BOARDCONFIG="${BOARD_CONFIG}" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel "$(nproc 2>/dev/null || sysctl -n hw.ncpu)"

echo "=== 4/4: UF2 kopieren ==="
mkdir -p dist
UF2_FILE=$(find build -maxdepth 2 -name "*.uf2" | head -n 1)
OUT_FILE="dist/GP2040-CE_${BOARD_CONFIG}_${MACRO_SLOTS}Macros_${MACRO_INPUTS}Inputs_WebUI.uf2"
cp "${UF2_FILE}" "${OUT_FILE}"
echo "[OK] Fertige Firmware: ${OUT_FILE}"
ls -lh "${OUT_FILE}"
