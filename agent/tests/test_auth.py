import asyncio
import time

import google.auth.exceptions
import pytest

from agw_agent.auth import ID_TOKEN_HEADER, GatewayClient, IdToken, audience_for, jwt_expiry


def counting_token(monkeypatch, tokens: list[str]) -> tuple[IdToken, list[int]]:
    token = IdToken("https://gw.example")
    calls = [0]

    def fetch(self):
        calls[0] += 1
        return tokens[calls[0] - 1]

    monkeypatch.setattr(IdToken, "_fetch", fetch)
    return token, calls


def test_audience_is_the_service_url_without_path():
    assert audience_for("https://gw-abc-ew.a.run.app/v1") == "https://gw-abc-ew.a.run.app"
    assert audience_for("https://gw-abc-ew.a.run.app") == "https://gw-abc-ew.a.run.app"


def test_jwt_expiry_reads_exp_claim(make_jwt):
    assert jwt_expiry(make_jwt(1234567890)) == 1234567890


def test_token_is_reused_while_fresh(monkeypatch, make_jwt):
    fresh = make_jwt(time.time() + 3600)
    token, calls = counting_token(monkeypatch, [fresh, "unexpected"])
    assert asyncio.run(token.get()) == fresh
    assert asyncio.run(token.get()) == fresh
    assert calls[0] == 1


def test_token_is_refreshed_near_expiry(monkeypatch, make_jwt):
    # A long-lived instance must not send a token that expires mid-request.
    expiring = make_jwt(time.time() + 60)
    fresh = make_jwt(time.time() + 3600, sub="second")
    token, calls = counting_token(monkeypatch, [expiring, fresh])
    assert asyncio.run(token.get()) == expiring
    assert asyncio.run(token.get()) == fresh
    assert calls[0] == 2


def test_client_adds_id_token_and_keeps_other_headers(monkeypatch, make_jwt):
    jwt = make_jwt(time.time() + 3600)
    token, _ = counting_token(monkeypatch, [jwt])
    client = GatewayClient(token)
    out = asyncio.run(client._with_id_token({"extra_headers": {"X-Other": "1"}, "stream": True}))
    assert out["extra_headers"] == {"X-Other": "1", ID_TOKEN_HEADER: f"Bearer {jwt}"}
    assert out["stream"] is True


def test_concurrent_callers_share_one_fetch(monkeypatch, make_jwt):
    token, calls = counting_token(monkeypatch, [make_jwt(time.time() + 3600)])

    async def many():
        return await asyncio.gather(*(token.get() for _ in range(20)))

    assert len(set(asyncio.run(many()))) == 1
    assert calls[0] == 1


def failing_after_first(monkeypatch, first: str) -> IdToken:
    token = IdToken("https://gw.example")
    tokens = iter([first])

    def fetch(self):
        try:
            return next(tokens)
        except StopIteration:
            raise google.auth.exceptions.TransportError("metadata server down") from None

    monkeypatch.setattr(IdToken, "_fetch", fetch)
    return token


def test_failed_refresh_keeps_a_still_valid_token(monkeypatch, make_jwt):
    # Inside the refresh margin but not expired: a metadata blip must not fail calls.
    current = make_jwt(time.time() + 120)
    token = failing_after_first(monkeypatch, current)
    assert asyncio.run(token.get()) == current
    assert asyncio.run(token.get()) == current


def test_failed_refresh_raises_when_token_is_about_to_expire(monkeypatch, make_jwt):
    token = failing_after_first(monkeypatch, make_jwt(time.time() + 10))
    asyncio.run(token.get())
    with pytest.raises(google.auth.exceptions.TransportError):
        asyncio.run(token.get())


def test_sync_completion_is_refused():
    # A call without the ID token would only fail later, at Cloud Run, with a 403.
    with pytest.raises(NotImplementedError):
        GatewayClient(IdToken("https://gw.example")).completion(model="m", messages=[], tools=None)


def test_anthropic_hook_fetches_a_current_token_per_request(monkeypatch, make_jwt):
    # An instance outlives a one-hour token: each request must carry the token
    # IdToken holds now, not the first one it saw.
    import httpx2

    from agw_agent.auth import anthropic_gateway_http_client

    first = make_jwt(time.time() + 60)  # inside the refresh margin
    second = make_jwt(time.time() + 3600, sub="second")
    token, calls = counting_token(monkeypatch, [first, second])
    seen = []

    def handler(request):
        seen.append(request.headers[ID_TOKEN_HEADER])
        return httpx2.Response(200, json={})

    client = anthropic_gateway_http_client(token, transport=httpx2.MockTransport(handler))

    async def go():
        await client.post("https://gw.example/x", headers={ID_TOKEN_HEADER: "Bearer stale"})
        await client.post("https://gw.example/x")

    asyncio.run(go())
    # The hook's token replaces a caller-supplied one, and is refreshed near expiry.
    assert seen == [f"Bearer {first}", f"Bearer {second}"]
    assert calls[0] == 2
