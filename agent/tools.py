"""Moved to agent/data/tools.py. Alias so `from agent import tools` keeps working; it is the same module object."""
import sys

from .data import tools as _module

sys.modules[__name__] = _module
