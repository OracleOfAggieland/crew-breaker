"""Put the app's backend folder on the path, the way the gateway loads it."""

import sys
from pathlib import Path

from hypothesis import settings

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# `pytest --hypothesis-profile thorough` searches twenty times as hard.
settings.register_profile("thorough", max_examples=2000, deadline=None)
