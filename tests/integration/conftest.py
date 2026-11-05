import os

import pytest

GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://gateway.localhost")
SIMULATOR_URL = os.environ.get("SIMULATOR_URL", "https://simulator.localhost")
MERCHANT_URL = os.environ.get("MERCHANT_URL", "https://shop.localhost")


@pytest.fixture
def urls():
    return {"gateway": GATEWAY_URL, "simulator": SIMULATOR_URL, "merchant": MERCHANT_URL}
