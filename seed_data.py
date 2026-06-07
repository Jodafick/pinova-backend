#!/usr/bin/env python
"""Point d'entrée racine — compatible Render (`python seed_data.py`).

Délègue au script principal dans ``scripts/seed_data.py``.
"""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent / 'scripts' / 'seed_data.py'),
    run_name='__main__',
)
