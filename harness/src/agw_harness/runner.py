"""Sends requests at a fixed concurrency and records one result per request.

Timing starts after headers (and any token refresh) are ready and ends when the
full response has arrived. For streams, time to first token is the first event
that carries answer text. Warm-up requests run the same way and are discarded.
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass

import httpx

from agw_harness.protocols import RequestProtocol, Usage
from agw_harness.settings import PROMPTS

HeaderSource = Callable[[], Awaitable[dict[str, str]]]

MAX_ERROR_CHARS = 500

# Credentials a gateway may echo in an error body: key hashes (LiteLLM puts the key's
# SHA-256, lowercase hexdigest, in rate-limit and budget 429s), raw keys (LiteLLM's
# masked "sk-...ABCD" form is left alone), Google API keys, ID tokens (JWTs) and access
# tokens. Error text is committed with the raw results, so these never reach disk.
_SECRET_PATTERNS = (
    (re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])"), "<sha256 redacted>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "sk-<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+"), "<jwt redacted>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), "<api key redacted>"),
    (re.compile(r"\bya29\.[A-Za-z0-9_.-]+"), "<token redacted>"),
)


def redact(text: str) -> str:
    """Replace credentials in error text (see _SECRET_PATTERNS)."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def clip_error(error: str | None, limit: int = MAX_ERROR_CHARS) -> str | None:
    """Redact, then truncate: in that order, so no partial credential survives a cut."""
    return redact(error)[:limit] if error else error


@dataclass
class Result:
    index: int
    prompt_id: int
    started_at: float
    status: int
    ok: bool
    latency_s: float
    ttft_s: float | None
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    answer_chars: int
    error: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def _merge(usage: Usage, new: Usage | None) -> Usage:
    if new is None:
        return usage
    return Usage(
        new.input_tokens if new.input_tokens is not None else usage.input_tokens,
        new.output_tokens if new.output_tokens is not None else usage.output_tokens,
        new.thinking_tokens if new.thinking_tokens is not None else usage.thinking_tokens,
    )


def _stream_error(event: object) -> str | None:
    """An error reported inside a stream (Anthropic, Gemini, ADK and OpenAI shapes)."""
    if isinstance(event, dict) and (
        "error" in event or event.get("type") == "error" or event.get("errorCode")
    ):
        return json.dumps(event)  # cut later, by clip_error, after redaction
    return None


async def _sse_events(lines):
    """Yield the data of each server-sent event, joining multi-line `data:` fields."""
    data: list[str] = []
    async for line in lines:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            yield "\n".join(data)
            data = []
    if data:
        yield "\n".join(data)


async def send_one(
    client: httpx.AsyncClient,
    proto: RequestProtocol,
    headers: dict[str, str],
    index: int,
    stream: bool,
) -> Result:
    prompt_id = index % len(PROMPTS)
    url, body = proto.url(stream), proto.body(PROMPTS[prompt_id], stream)
    if stream:
        # Uncompressed streams for every target, so no target's TTFT waits on decompression.
        headers = {**headers, "Accept-Encoding": "identity"}
    started_at = time.time()
    t0 = time.perf_counter()
    ttft = None
    usage = Usage()
    answer = ""
    status, error = 0, None
    try:
        if stream:
            async with client.stream("POST", url, json=body, headers=headers) as r:
                status = r.status_code
                if status >= 400:
                    error = (await r.aread()).decode(errors="replace")
                else:
                    async for data in _sse_events(r.aiter_lines()):
                        if not data or data == "[DONE]":
                            continue
                        event = json.loads(data)
                        if error := _stream_error(event):
                            break
                        chunk = proto.text(event)
                        if chunk and ttft is None:
                            ttft = time.perf_counter() - t0
                        answer += chunk
                        usage = _merge(usage, proto.usage(event))
        else:
            r = await client.post(url, json=body, headers=headers)
            status = r.status_code
            if status >= 400:
                error = r.text
            else:
                data = r.json()
                answer = proto.text(data)
                usage = _merge(usage, proto.usage(data))
    except Exception as e:  # noqa: BLE001 - every failure is recorded, never fatal to the run
        error = f"{type(e).__name__}: {e}"
    latency = time.perf_counter() - t0
    error = clip_error(error)  # after timing: redaction is not part of the measurement
    ok = error is None and 200 <= status < 300 and bool(answer)
    if error is None and not ok:
        error = "empty answer"
    return Result(
        index=index,
        prompt_id=prompt_id,
        started_at=started_at,
        status=status,
        ok=ok,
        latency_s=round(latency, 4),
        ttft_s=round(ttft, 4) if ttft is not None else None,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        thinking_tokens=usage.thinking_tokens,
        answer_chars=len(answer),
        error=error,
    )


def _auth_failure(index: int, e: Exception) -> Result:
    """A request that never left because its credentials couldn't be fetched (not timed)."""
    return Result(
        index=index,
        prompt_id=index % len(PROMPTS),
        started_at=time.time(),
        status=0,
        ok=False,
        latency_s=0.0,
        ttft_s=None,
        input_tokens=None,
        output_tokens=None,
        thinking_tokens=None,
        answer_chars=0,
        error=clip_error(f"auth: {type(e).__name__}: {e}"),
    )


async def run(
    proto: RequestProtocol,
    headers: HeaderSource,
    *,
    n: int,
    concurrency: int,
    stream: bool,
    warmup: int,
    client: httpx.AsyncClient | None = None,
    offset: int = 0,
) -> tuple[list[Result], float]:
    """Run `warmup` discarded requests, then `n` measured ones. Returns (results, wall_s).

    Measured requests are numbered from `offset` (which also picks their prompts), so
    a run split into blocks keeps one index sequence.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
    )
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int) -> Result:
        async with sem:
            try:
                h = await headers()
            except Exception as e:  # noqa: BLE001 - recorded per request, not fatal
                return _auth_failure(i, e)
            return await send_one(client, proto, h, i, stream)

    try:
        await asyncio.gather(*(one(-1 - i) for i in range(warmup)))
        t0 = time.perf_counter()
        results = await asyncio.gather(*(one(offset + i) for i in range(n)))
        wall = time.perf_counter() - t0
    finally:
        if own_client:
            await client.aclose()
    return list(results), wall
