"""Singleton config loader – reads franz.cfg once at import time.

Search order:
  1. $FRANZ_DIR/franz.cfg          (runtime data dir, e.g. ~/Franz/franz.cfg)
  2. <package-root>/franz.cfg      (dev layout: repo root)
  3. <package-root>/config/franz.cfg  (Docker layout)
"""

from __future__ import annotations

import configparser
import os
import pathlib

_FRANZ_HOME = pathlib.Path(os.environ.get("FRANZ_DIR", pathlib.Path.home() / "Franz"))

_CFG_CANDIDATES = [
    _FRANZ_HOME / "franz.cfg",
    pathlib.Path(__file__).parent.parent / "franz.cfg",
    pathlib.Path(__file__).parent.parent / "config" / "franz.cfg",
]

cfg = configparser.ConfigParser()
for _p in _CFG_CANDIDATES:
    if _p.is_file():
        cfg.read(_p)
        break
