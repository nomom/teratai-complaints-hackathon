"""Moved to agent/decision/dates.py. Alias so `from agent.dates import ...` keeps working; it is the same module object."""
import sys

from .decision import dates as _module

sys.modules[__name__] = _module
