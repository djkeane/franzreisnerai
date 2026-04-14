#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================
#   Franz v5.0 – Agentic Terminal AI
#   Fejlesztő: DömösAiTech 2026
#   GitHub: https://github.com/djkeane/franzreisnerai
# ==============================================================
"""Entry point – delegates to src.cli.main()."""

import sys
import pathlib

# Ha a szkript közvetlen futtatásából hívják (nem csomagként), add a könyvtárat a path-hoz
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from src.cli import main

if __name__ == "__main__":
    main()
