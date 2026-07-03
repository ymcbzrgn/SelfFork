"""Make this benchmark's sibling modules importable under ``--import-mode=importlib``.

pytest's importlib mode deliberately does not add the test file's directory
to ``sys.path``, so ``import run_eval`` / ``import synth`` /
``import validate_dataset`` from ``test_run_eval.py`` would otherwise fail.
This conftest (auto-loaded for the dir) puts the benchmark dir on the path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
