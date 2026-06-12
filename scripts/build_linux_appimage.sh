#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --upgrade pip
if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt; fi
python3 -m pip install pyinstaller
pyinstaller --onefile --console --name "MTS-CoinSort" MTS_Coin_Sort.py
