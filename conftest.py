"""pytest configuration: add project root to sys.path."""
import sys
from pathlib import Path

# Ensure `app` package is importable from the project root
sys.path.insert(0, str(Path(__file__).parent))
