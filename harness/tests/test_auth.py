import asyncio
import base64
import json
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace

import google.auth.exceptions
import pytest

from agw_harness import auth
from agw_harness.settings import load

NOW = 1_800_000_000.0


class FakeClock:
    def __init__(self):
        self.now = NOW

    def time(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    # Replace the module's reference only; patching time.time globally would also hit asyncio.
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=c.time))
    return c


def jwt(exp: float) -> str:
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'RS256'})}.{b64({'exp': exp})}.sig"


class FakeCreds:
    """Access tokens that live `lifetime` seconds from the fake clock's time of refresh."""

    def __init__(self, clock, lifetime=3600.0):
        self.clock, self.lifetime = clock, lifetime
        self.token, self.expiry, self.refreshes = None, None, 0

    def refresh(self, request):
        self.refreshes += 1
        self.token = f"access-{self.refreshes}"
        expires_at = self.clock.now + self.lifetime
        self.expiry = datetime.fromtimestamp(expires_at, UTC).replace(tzinfo=None)


@pytest.fixture
def creds(monkeypatch, clock):
    c = FakeCreds(clock)
    monkeypatch.setattr(auth.google.auth, "default", lambda scopes=None: (c, "p"))
    return c


@pytest.fixture
def id_tokens(monkeypatch, clock):
    """fetch_id_token returns JWTs valid for an hour; requested audiences are recorded."""
    calls = []

    def fetch(request, audience):
        calls.append(audience)
        return jwt(clock.now + 3600)

    monkeypatch.setattr(auth.id_token, "fetch_id_token", fetch)
    return calls


def get(source):
    return asyncio.run(source.get())


def test_audience_drops_the_path():
    assert auth.audience_for("https://gw-abc.a.run.app/v1") == "https://gw-abc.a.run.app"
    assert auth.audience_for("https://agent.example") == "https://agent.example"


def test_jwt_expiry_reads_exp():
    assert auth.jwt_expiry(jwt(NOW + 5)) == NOW + 5


def test_access_token_fetched_once_then_cached(creds, clock):
    token = auth.AccessToken()
    assert get(token) == "access-1"
    clock.now += 3600 - auth.REFRESH_MARGIN_S - 1
    assert get(token) == "access-1"
    assert creds.refreshes == 1


def test_access_token_refreshes_near_expiry(creds, clock):
    token = auth.AccessToken()
    get(token)
    clock.now += 3600 - auth.REFRESH_MARGIN_S + 1
    assert get(token) == "access-2"


def test_access_token_without_expiry_is_not_refreshed_every_call(creds):
    token = auth.AccessToken()
    get(token)
    creds.expiry = None
    get(token)
    assert creds.refreshes == 1


def test_id_token_cached_then_refreshed_from_its_own_expiry(id_tokens, clock):
    token = auth.IdToken("https://agent.example")
    first = get(token)
    clock.now += 3600 - auth.REFRESH_MARGIN_S - 1
    assert get(token) == first and len(id_tokens) == 1
    clock.now += 2
    get(token)
    assert len(id_tokens) == 2


def test_cached_gcloud_token_near_expiry_is_refetched(monkeypatch, clock):
    # gcloud can return a cached token with little time left: its exp decides, not our fetch time.
    tokens = iter([jwt(clock.now + 60), jwt(clock.now + 3600)])
    monkeypatch.setattr(auth.IdToken, "_fetch", lambda self: next(tokens))
    token = auth.IdToken("https://agent.example")
    get(token)
    assert auth.jwt_expiry(get(token)) == clock.now + 3600


def test_id_token_falls_back_to_gcloud_for_user_credentials(monkeypatch, clock):
    def no_sa(request, audience):
        raise google.auth.exceptions.DefaultCredentialsError("user credentials")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(stdout=jwt(clock.now + 3600) + "\n")

    monkeypatch.setattr(auth.id_token, "fetch_id_token", no_sa)
    monkeypatch.setattr(auth.subprocess, "run", fake_run)
    assert auth.jwt_expiry(get(auth.IdToken("https://agent.example"))) == clock.now + 3600
    assert calls[0][0] == ["gcloud", "auth", "print-identity-token"]
    assert calls[0][1]["check"] is True


def test_other_id_token_errors_are_not_masked_by_gcloud(monkeypatch):
    def metadata_down(request, audience):
        raise google.auth.exceptions.TransportError("metadata server unavailable")

    def must_not_run(*args, **kwargs):
        raise AssertionError("gcloud fallback used for a non-credentials error")

    monkeypatch.setattr(auth.id_token, "fetch_id_token", metadata_down)
    monkeypatch.setattr(auth.subprocess, "run", must_not_run)
    with pytest.raises(google.auth.exceptions.TransportError):
        get(auth.IdToken("https://agent.example"))


def test_gcloud_failure_propagates(monkeypatch):
    def no_sa(request, audience):
        raise google.auth.exceptions.DefaultCredentialsError("user credentials")

    def failing_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(auth.id_token, "fetch_id_token", no_sa)
    monkeypatch.setattr(auth.subprocess, "run", failing_run)
    with pytest.raises(subprocess.CalledProcessError):
        get(auth.IdToken("https://agent.example"))


def settings(**extra):
    # As in the harness job, so ID tokens come from fetch_id_token (the id_tokens fixture).
    return load(
        {
            "CLOUD_RUN_JOB": "agw-harness",
            "AGW_PROJECT": "my-gcp-project",
            "AGW_AGENT_URL": "https://agent.example/",
            "AGW_GATEWAY_URL": "https://gw.example/v1",
            **extra,
        }
    )


def test_direct_headers_use_access_token_and_quota_project(creds):
    h = get(auth.Headers("direct", settings()))
    assert h["Authorization"] == "Bearer access-1"
    assert h["x-goog-user-project"] == "my-gcp-project"


def test_agent_headers_use_id_token_for_the_service_url(id_tokens):
    h = get(auth.Headers("agent", settings(AGW_GATEWAY_API_KEY="ignored")))
    assert h["Authorization"].startswith("Bearer ey")
    assert "x-goog-user-project" not in h and "X-Serverless-Authorization" not in h
    assert id_tokens == ["https://agent.example"]


def test_gateway_headers_without_api_key(id_tokens):
    h = get(auth.Headers("gateway", settings()))
    assert h["Authorization"].startswith("Bearer ey")
    assert id_tokens == ["https://gw.example"]  # path dropped: Cloud Run checks the service URL


def test_gateway_api_key_moves_id_token_to_serverless_header(id_tokens):
    h = get(auth.Headers("gateway", settings(AGW_GATEWAY_API_KEY="sk-gw")))
    assert h["Authorization"] == "Bearer sk-gw"
    assert h["X-Serverless-Authorization"].startswith("Bearer ey")
    assert "x-goog-user-project" not in h


@pytest.mark.parametrize(
    ("env", "source"),
    [
        # A local machine, including a Compute Engine VM (no K_SERVICE): the developer.
        ({}, "gcloud"),
        # A Cloud Run service (a cloud workstation): its metadata server is the wrong identity.
        ({"K_SERVICE": "jimtop"}, "gcloud"),
        # A key file was chosen on purpose, on any machine.
        ({"GOOGLE_APPLICATION_CREDENTIALS": "/k.json"}, "metadata"),
        # The harness job (Cloud Run sets CLOUD_RUN_JOB, not K_SERVICE): its account is right.
        ({"CLOUD_RUN_JOB": "agw-harness"}, "metadata"),
        # Defensive: if both were set, the job wins.
        ({"K_SERVICE": "x", "CLOUD_RUN_JOB": "agw-harness"}, "metadata"),
        # A key file was chosen on purpose, even on a workstation.
        ({"K_SERVICE": "jimtop", "GOOGLE_APPLICATION_CREDENTIALS": "/k.json"}, "metadata"),
        ({"K_SERVICE": "jimtop", "AGW_ID_TOKEN_SOURCE": "metadata"}, "metadata"),
        ({"AGW_ID_TOKEN_SOURCE": "gcloud"}, "gcloud"),
    ],
)
def test_id_token_source_follows_where_the_harness_runs(env, source):
    assert load(env).id_token_source == source


def test_unknown_id_token_source_rejected():
    with pytest.raises(ValueError, match="AGW_ID_TOKEN_SOURCE"):
        load({"AGW_ID_TOKEN_SOURCE": "keyfile"})


def test_gcloud_source_never_asks_the_metadata_server(monkeypatch, clock):
    def must_not_fetch(request, audience):
        raise AssertionError("metadata server used for a gcloud-sourced token")

    monkeypatch.setattr(auth.id_token, "fetch_id_token", must_not_fetch)
    monkeypatch.setattr(
        auth.subprocess, "run", lambda cmd, **kw: SimpleNamespace(stdout=jwt(clock.now + 3600))
    )
    token = auth.IdToken("https://gw.example", source="gcloud")
    assert auth.jwt_expiry(get(token)) == clock.now + 3600


def test_headers_pass_the_source_to_id_tokens():
    h = auth.Headers("gateway", settings(AGW_ID_TOKEN_SOURCE="gcloud"))
    assert h._token._source == "gcloud"
