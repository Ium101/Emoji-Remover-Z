#!/bin/bash
# Emoji Remover Z - Build Script (Linux / macOS)
set -e

echo "===================================================="
echo "  Emoji Remover Z - Build Script"
echo "===================================================="
echo

# Prefer python3.14, fall back to python3.12, then python3
if command -v python3.14 &>/dev/null; then
    PY=python3.14
elif command -v python3.12 &>/dev/null; then
    PY=python3.12
elif command -v python3 &>/dev/null; then
    PY=python3
else
    echo "ERROR: Python 3 not found. Install it from https://python.org"
    exit 1
fi

echo "[1/4] Using $($PY --version)"
echo

echo "[2/4] Creating virtual environment..."
$PY -m venv .venv
source .venv/bin/activate

echo "[3/4] Installing PyInstaller..."
pip install pyinstaller --quiet

echo "[4/4] Building executable..."
python -m PyInstaller --onefile --windowed --name "EmojiRemoverZ" emoji-remover-z.py

deactivate

echo
echo "Done!"
echo
echo "Your executable is at:  dist/EmojiRemoverZ"
echo
