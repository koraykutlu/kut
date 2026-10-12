#!/bin/sh
# macOS: çift tıkla (ilk sefer: Terminal'de `chmod +x Kut.command`). Ağı tarayıcıda açar.
cd "$(dirname "$0")/.." && exec python3 kut.pyw "$@"
