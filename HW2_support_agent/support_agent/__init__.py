"""Meridian customer-support agent - HW2 starter package."""

import sys

if sys.version_info < (3, 10):
    raise RuntimeError(
        "HW2 needs Python 3.10 or newer; this is %d.%d. Run "
        "`python scripts/check_env.py` for what to do about it."
        % (sys.version_info[0], sys.version_info[1]))

__version__ = "1.1.0"
