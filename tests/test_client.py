import pytest

from nep_local.client import NepGatewayClient
from nep_local.exceptions import NepResponseMissing
from nep_local.models import InventoryModule


class _Response:
    def __init__(self, status: int, body: str) -> None:
        self.status, self.body = status, body

    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False
    async def text(self): return self.body


class _Session:
    def __init__(self, responses): self.responses, self.urls = iter(responses), []
    def get(self, url): self.urls.append(url); return next(self.responses)


@pytest.mark.asyncio
async def test_client_uses_actual_gateway_paths_and_cachebuster() -> None:
    session = _Session([
        _Response(200, '<div class="box" addr="9" title="M_ID:REDACTED_MODULE_A"></div>'),
        _Response(200, '{"addr":"0","now":0,"today":0,"total":0,"status":"0000"}'),
        _Response(200, '{"addr":"9","now":0,"today":0,"total":0,"status":"0000"}'),
    ])
    client = NepGatewayClient(session, "http://gateway.invalid", cachebuster=lambda: "cache-token")
    await client.inventory()
    await client.aggregate()
    await client.module(InventoryModule(address="9", raw_id="REDACTED_MODULE_A"))
    assert session.urls == [
        "http://gateway.invalid/nep/status/index/",
        "http://gateway.invalid/nep/realdata/tt/0/cache-token",
        "http://gateway.invalid/nep/realdata/tt/9/cache-token",
    ]


@pytest.mark.asyncio
async def test_client_uses_addressed_min_dat_and_raises_for_empty_response() -> None:
    session = _Session([_Response(200, "")])
    client = NepGatewayClient(session, "http://gateway.invalid")
    with pytest.raises(NepResponseMissing):
        await client.min_dat(InventoryModule(address="9", raw_id="REDACTED_MODULE_A"))
    assert session.urls == ["http://gateway.invalid/data/9/min.dat"]
