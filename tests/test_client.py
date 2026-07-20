import pytest

from nep_local.client import NepGatewayClient
from nep_local.exceptions import NepResponseMissing


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
    def __init__(self, response): self.response = response
    def get(self, url):
        self.url = url
        return self.response


@pytest.mark.asyncio
async def test_client_uses_injected_session_and_raises_for_empty_response() -> None:
    session = _Session(_Response(200, ""))
    client = NepGatewayClient(session, "http://gateway.invalid")
    with pytest.raises(NepResponseMissing):
        await client.inventory()
    assert session.url == "http://gateway.invalid/"
