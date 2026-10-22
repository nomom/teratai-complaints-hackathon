"""Moved to agent/decision/policy.py. Alias so `from agent import policy` keeps working; it is the same module object."""
import sys

from .decision import policy as _module

sys.modules[__name__] = _module
