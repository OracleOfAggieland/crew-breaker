"""Put the app's root on the path, so `backend` imports as the gateway loads it."""

import sys
from pathlib import Path

from hypothesis import settings

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# `pytest --hypothesis-profile thorough` searches twenty times as hard.
settings.register_profile("thorough", max_examples=2000, deadline=None)
