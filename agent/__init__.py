"""The complaints agent. Settings come from the environment; a .env file at the repo root fills in any not set.

A variable already set in the shell wins over .env, e.g. `$env:LLM_PROVIDER = ""` turns the LLM off for one run.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
