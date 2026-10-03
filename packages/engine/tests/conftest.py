import os
import random

import pytest


@pytest.fixture(autouse=True)
def _reproducible_fuzz():
    """py-fsrs fuzzes intervals with the global random generator: seed it so every run is the same.
    LC_TEST_SEED=<n> checks the tests hold for other draws too."""
    random.seed(int(os.environ.get("LC_TEST_SEED", "0")))
