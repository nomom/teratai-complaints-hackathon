"""The case-management app. Loads the repo-root .env like the agent does (see agent/__init__.py)."""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
