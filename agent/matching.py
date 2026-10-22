"""Moved to agent/decision/matching.py. Alias so `from agent import matching` keeps working; it is the same module object."""
import sys

from .decision import matching as _module

sys.modules[__name__] = _module
