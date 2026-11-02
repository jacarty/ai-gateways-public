"""Cloud Run auth for calls to a gateway.

Gateways run on Cloud Run with IAM auth, so every call needs an ID token for the
gateway's URL. The gateway's own key already takes Authorization (the OpenAI
client sets it), so the ID token goes in X-Serverless-Authorization, which Cloud
Run checks instead. The token is minted from the agent's service account and
refreshed from its real expiry, since an instance can outlive the one-hour token.
Both clients get it: ADK's LiteLLM client (GatewayClient) and, for Claude sent to a
gateway in its own Vertex format, the Anthropic SDK's (anthropic_gateway_http_client).
"""

import asyncio
import base64
import json
import logging
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import google.auth.exceptions
import google.auth.transport.requests
from anthropic import DefaultAsyncHttpxClient
from google.adk.models.lite_llm import LiteLLMClient
from google.oauth2 import id_token

# Refresh a token once it has less than this left (tokens live about an hour).
REFRESH_MARGIN_S = 5 * 60
# If a refresh fails, keep using the old token while it has at least this left.
MIN_REMAINING_S = 30

log = logging.getLogger(__name__)

ID_TOKEN_HEADER = "X-Serverless-Authorization"


def audience_for(url: str) -> str:
    """Cloud Run checks the ID token's audience against the service URL, without a path."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def jwt_expiry(token: str) -> float:
    """The `exp` claim of a JWT (unverified: only used to decide when to refresh)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])


class IdToken:
    """An ID token for one audience, fetched on first use and refreshed before it expires.

    A fresh token is returned on the event loop; only a refresh (a metadata-server
    call) runs in a worker thread, one at a time.
    """

    def __init__(self, audience: str) -> None:
        self.audience = audience
        self._token = ""
        self._expiry = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> str:
        # On Cloud Run this asks the metadata server for the agent's service account.
        return id_token.fetch_id_token(google.auth.transport.requests.Request(), self.audience)

    def _remaining(self) -> float:
        return self._expiry - time.time()

    def _refresh(self) -> str:
        with self._lock:
            # Another caller may have refreshed while this one waited for the lock.
            if self._remaining() >= REFRESH_MARGIN_S:
                return self._token
            try:
                token = self._fetch()
            except google.auth.exceptions.GoogleAuthError as e:
                if self._token and self._remaining() >= MIN_REMAINING_S:
                    log.warning("ID token refresh failed, using the current token: %s", e)
                    return self._token
                raise
            # Token before expiry: get() reads the expiry first without the lock, so it
            # never pairs a new expiry with the old token.
            self._token = token
            self._expiry = jwt_expiry(token)
            return token

    async def get(self) -> str:
        if self._remaining() >= REFRESH_MARGIN_S:
            return self._token
        return await asyncio.to_thread(self._refresh)


class GatewayClient(LiteLLMClient):
    """ADK's LiteLLM client, adding a current ID token to every call.

    ADK's LiteLlm sends streaming and non-streaming calls through acompletion only.
    """

    def __init__(self, token: IdToken) -> None:
        super().__init__()
        self.token = token

    async def _with_id_token(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        headers = dict(kwargs.get("extra_headers") or {})
        headers[ID_TOKEN_HEADER] = f"Bearer {await self.token.get()}"
        return {**kwargs, "extra_headers": headers}

    async def acompletion(self, model: Any, messages: Any, tools: Any, **kwargs: Any) -> Any:
        kwargs = await self._with_id_token(kwargs)
        return await super().acompletion(model=model, messages=messages, tools=tools, **kwargs)

    def completion(self, *args: Any, **kwargs: Any) -> Any:
        # ADK 2.10 never calls this; fail loudly if a later version does, rather
        # than sending a call without the ID token.
        raise NotImplementedError("gateway calls must go through acompletion")


def anthropic_gateway_http_client(token: IdToken, **kwargs: Any) -> DefaultAsyncHttpxClient:
    """An HTTP client for the Anthropic SDK that adds a current ID token to every request.

    For Claude sent to a gateway in its own Vertex format: the SDK puts the gateway
    key in Authorization (as its access token), so the ID token goes in
    X-Serverless-Authorization, as for the LiteLLM path. The SDK's default client
    keeps its own timeouts and connection limits; kwargs go to it (tests pass a transport).
    """

    async def add_id_token(request: Any) -> None:
        request.headers[ID_TOKEN_HEADER] = f"Bearer {await token.get()}"

    # No redirects: the hook would send the ID token on to wherever a redirect points.
    return DefaultAsyncHttpxClient(
        event_hooks={"request": [add_id_token]}, follow_redirects=False, **kwargs
    )
