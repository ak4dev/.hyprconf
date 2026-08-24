"""
Shared pytest bootstrap for hyprconf tests.

Puts ``lib/`` on ``sys.path`` so ``hyprconf`` (``__version__``,
``firefox_theme``) imports regardless of how pytest was invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LIB_DIR = REPO_ROOT / "lib"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
