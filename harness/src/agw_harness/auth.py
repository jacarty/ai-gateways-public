"""Credentials for each target, fetched before the clock starts and refreshed in time.

direct   OAuth access token from Application Default Credentials.
agent    ID token for the Cloud Run URL (the service is IAM-authenticated).
gateway  ID token for its Cloud Run URL; with an API key, the key takes Authorization
         and the ID token moves to X-Serverless-Authorization, which Cloud Run reads.

Tokens are refreshed from their real expiry (not a timer), one refresh at a time.
"""

import asyncio
import base64
import json
import subprocess
import threading
import time
from datetime import UTC
from urllib.parse import urlsplit

import google.auth
import google.auth.exceptions
import google.auth.transport.requests
from google.oauth2 import id_token

from agw_harness.settings import Settings

# Refresh a token once it has less than this left (tokens live about an hour).
REFRESH_MARGIN_S = 5 * 60


def audience_for(url: str) -> str:
    """Cloud Run checks the ID token's audience against the service URL, without a path."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def jwt_expiry(token: str) -> float:
    """The `exp` claim of a JWT (unverified: only used to decide when to refresh)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])


class AccessToken:
    def __init__(self) -> None:
        self._creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._lock = threading.Lock()

    def _get(self) -> str:
        with self._lock:
            creds = self._creds
            expiry = creds.expiry  # naive UTC, or None
            near_expiry = (
                expiry is not None
                and expiry.replace(tzinfo=UTC).timestamp() - time.time() < REFRESH_MARGIN_S
            )
            if not creds.token or near_expiry:
                creds.refresh(google.auth.transport.requests.Request())
            return creds.token

    async def get(self) -> str:
        return await asyncio.to_thread(self._get)


class IdToken:
    def __init__(self, audience: str, source: str = "metadata") -> None:
        self._audience = audience
        self._source = source
        self._token = ""
        self._lock = threading.Lock()

    def _gcloud(self) -> str:
        out = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    def _fetch(self) -> str:
        if self._source == "gcloud":
            return self._gcloud()
        try:
            # Works with the metadata server (Cloud Run job) and service account keys.
            return id_token.fetch_id_token(google.auth.transport.requests.Request(), self._audience)
        except google.auth.exceptions.DefaultCredentialsError:
            # Local runs as a user: ADC user credentials can't mint ID tokens, gcloud can.
            # Other errors (e.g. a metadata server failure in the job) are raised as they are.
            return self._gcloud()

    def _get(self) -> str:
        with self._lock:
            # gcloud may hand back a cached token with little time left, so read its expiry.
            if not self._token or jwt_expiry(self._token) - time.time() < REFRESH_MARGIN_S:
                self._token = self._fetch()
            return self._token

    async def get(self) -> str:
        return await asyncio.to_thread(self._get)


class Headers:
    """Builds request headers for one target; call get() outside the timed section."""

    def __init__(self, target: str, settings: Settings) -> None:
        self._target = target
        self._project = settings.project
        self._api_key = settings.gateway_api_key if target == "gateway" else None
        if target == "direct":
            self._token = AccessToken()
        else:
            url = settings.agent_url if target == "agent" else settings.gateway_url
            self._token = IdToken(audience_for(url or ""), settings.id_token_source)

    async def get(self) -> dict[str, str]:
        token = await self._token.get()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
            headers["X-Serverless-Authorization"] = f"Bearer {token}"
        else:
            headers["Authorization"] = f"Bearer {token}"
        if self._target == "direct":
            # Bill quota to the lab project, not whatever ADC's default quota project is.
            headers["x-goog-user-project"] = self._project
        return headers
