import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent / "back"
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402
