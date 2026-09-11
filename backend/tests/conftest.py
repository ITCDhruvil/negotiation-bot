import os
import sys
from pathlib import Path

os.environ["ARIA_ALLOW_MOCK"] = "1"
os.environ["LLM_PROVIDER"] = "mock"
os.environ.setdefault("USE_IN_MEMORY", "true")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
