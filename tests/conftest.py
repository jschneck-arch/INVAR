"""
conftest.py — pytest configuration for the INVAR test suite.

Adds /opt/invar to sys.path so that `import invar` works without
needing PYTHONPATH to be set manually.
"""
import sys
from pathlib import Path

repo_root = str(Path(__file__).resolve().parents[1])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
