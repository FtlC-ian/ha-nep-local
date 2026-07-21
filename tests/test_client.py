import asyncio

import pytest

from custom_components.nep_local.client import NepGatewayClient
from custom_components.nep_local.exceptions import NepResponseMissing
from custom_components.nep_local.models import InventoryModule


class _Response:
    def __init__(self, status: int, body: str) -> None:
        self.status, self.body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def text(self):
        return self.body


class _Session:
    def __init__(self, responses):
        self.responses, self.requests = iter(responses), []

    def get(self, url, *, headers=None, timeout=None):
        self.requests.append((url, headers))
        return next(self.responses)


@pytest.mark.asyncio
async def test_client_uses_actual_gateway_paths_and_cachebuster() -> None:
    session = _Session(
        [
            _Response(
                200,
                '<table><tr><td>Gateway</td><td>TESTGW000001</td></tr></table><div class="box" addr="9" title="M_ID:0XAAA00050"></div>',
            ),
            _Response(200, '{"addr":"0","now":0,"today":0,"total":0,"status":"0000"}'),
            _Response(200, '{"addr":"9","now":0,"today":0,"total":0,"status":"0000"}'),
        ]
    )
    client = NepGatewayClient(session, "http://gateway.invalid")
    client._cachebuster = lambda: "cache-token"
    await client.inventory()
    await client.aggregate()
    await client.module(InventoryModule(address="9", raw_id="REDACTED_MODULE_A"))
    assert session.requests == [
        ("http://gateway.invalid/nep/status/index/", None),
        ("http://gateway.invalid/nep/static/local/0_status/cache-token", None),
        ("http://gateway.invalid/nep/static/local/9_status/cache-token", None),
    ]


@pytest.mark.asyncio
async def test_client_uses_addressed_min_dat_and_raises_for_empty_response() -> None:
    session = _Session([_Response(200, "")])
    client = NepGatewayClient(session, "http://gateway.invalid")
    with pytest.raises(NepResponseMissing):
        await client.min_dat(InventoryModule(address="9", raw_id="REDACTED_MODULE_A"))
    assert session.requests == [
        ("http://gateway.invalid/data/9/min.dat", {"Range": "bytes=-1024"})
    ]


@pytest.mark.asyncio
async def test_client_limits_parallel_gateway_requests() -> None:
    active = 0
    peak_active = 0

    class _SlowResponse(_Response):
        async def __aenter__(self):
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0.01)
            return self

        async def __aexit__(self, *_):
            nonlocal active
            active -= 1
            return False

    session = _Session([_SlowResponse(200, "ok") for _ in range(8)])
    client = NepGatewayClient(session, "http://gateway.invalid")

    await asyncio.gather(*(client._get_text(f"/{index}") for index in range(8)))

    assert peak_active == 4
