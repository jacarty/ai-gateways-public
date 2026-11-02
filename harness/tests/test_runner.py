import asyncio
import json

import httpx

from agw_harness import runner
from agw_harness.protocols import AnthropicNative, OpenAIChat


async def static_headers():
    return {"Authorization": "Bearer t"}


def run(proto, handler, **kwargs):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runner.run(proto, static_headers, client=client, **kwargs)

    return asyncio.run(go())


def test_non_stream_records_tokens_and_discards_warmup(settings):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Brussels."}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3},
            },
        )

    results, wall = run(
        OpenAIChat(settings, "claude"), handler, n=4, concurrency=2, stream=False, warmup=2
    )
    assert len(seen) == 6  # 2 warm-up + 4 measured
    assert [r.index for r in results] == [0, 1, 2, 3]
    assert all(r.ok and r.status == 200 and r.output_tokens == 3 for r in results)
    assert all(r.ttft_s is None for r in results)
    assert wall > 0


def test_stream_records_ttft_and_merged_usage(settings):
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 9}}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Bru"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ssels."}},
        {"type": "message_delta", "usage": {"output_tokens": 3}},
    ]
    sse = "".join(f"event: x\ndata: {json.dumps(e)}\n\n" for e in events)

    def handler(request):
        assert request.url.path.endswith(":streamRawPredict")
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    (r,), _ = run(AnthropicNative(settings), handler, n=1, concurrency=1, stream=True, warmup=0)
    assert r.ok and r.answer_chars == len("Brussels.")
    assert r.ttft_s is not None and r.ttft_s <= r.latency_s
    assert (r.input_tokens, r.output_tokens) == (9, 3)


def test_http_errors_are_recorded_not_raised(settings):
    def handler(request):
        return httpx.Response(429, text="quota exceeded")

    (r,), _ = run(
        OpenAIChat(settings, "gemini"), handler, n=1, concurrency=1, stream=False, warmup=0
    )
    assert not r.ok and r.status == 429 and "quota" in r.error


def test_empty_answer_is_a_failure(settings):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    (r,), _ = run(
        OpenAIChat(settings, "gemini"), handler, n=1, concurrency=1, stream=False, warmup=0
    )
    assert not r.ok and r.error == "empty answer"


def test_concurrency_is_bounded(settings):
    in_flight, peak = 0, 0

    async def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    run(OpenAIChat(settings, "gemini"), handler, n=20, concurrency=3, stream=False, warmup=0)
    assert peak == 3


def sse(*events):
    return "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events)


def stream_handler(body):
    def handler(request):
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    return handler


def one(proto, handler, stream, **kwargs):
    (r,), _ = run(proto, handler, n=1, concurrency=1, stream=stream, warmup=0, **kwargs)
    return r


def test_gemini_sse_skips_thoughts_and_takes_final_usage(settings):
    from agw_harness.protocols import GeminiNative

    body = sse(
        {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "Bru"}]}}]},
        {
            "candidates": [{"content": {"parts": [{"text": "ssels."}]}}],
            "usageMetadata": {
                "promptTokenCount": 7,
                "candidatesTokenCount": 3,
                "thoughtsTokenCount": 2,
            },
        },
    )
    r = one(GeminiNative(settings), stream_handler(body), True)
    assert r.ok and r.answer_chars == len("Brussels.")
    assert (r.input_tokens, r.output_tokens, r.thinking_tokens) == (7, 3, 2)
    assert r.ttft_s is not None


def test_ttft_ignores_events_without_answer_text(settings):
    """A leading usage-only or thought-only event must not start the TTFT clock."""
    from agw_harness.protocols import GeminiNative

    body = sse(
        {"usageMetadata": {"promptTokenCount": 1}},
        {"candidates": [{"content": {"parts": [{"text": "x"}]}}]},
    )
    r = one(GeminiNative(settings), stream_handler(body), True)
    assert r.ttft_s is not None and r.ttft_s <= r.latency_s


def test_openai_sse_usage_only_final_chunk_and_done(settings):
    body = sse(
        {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
        {"choices": [{"delta": {"content": "Bru"}}]},
        {"choices": [{"delta": {"content": "ssels."}}]},
        # include_usage: final chunk has empty choices and only usage
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 4,
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        },
        "[DONE]",
    )
    r = one(OpenAIChat(settings, "gemini"), stream_handler(body), True)
    assert r.ok and r.answer_chars == len("Brussels.")
    assert (r.input_tokens, r.output_tokens, r.thinking_tokens) == (9, 4, 1)
    assert r.error is None


def test_agent_run_sse_events(settings):
    from agw_harness.protocols import AgentRun

    body = sse(
        {"content": {"parts": [{"text": "thinking", "thought": True}]}},
        {"content": {"parts": [{"text": "Brussels."}]}},
        {"usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}},
    )

    def handler(request):
        assert request.url.path == "/run_sse"
        return stream_handler(body)(request)

    r = one(AgentRun(settings, "gemini"), handler, True)
    assert r.ok and r.answer_chars == len("Brussels.")
    assert (r.input_tokens, r.output_tokens) == (5, 2)


def test_agent_run_non_stream_list_of_events(settings):
    from agw_harness.protocols import AgentRun

    def handler(request):
        assert request.url.path == "/run"
        return httpx.Response(
            200,
            json=[
                {
                    "content": {"parts": [{"text": "Brussels."}]},
                    "usageMetadata": {"promptTokenCount": 5},
                }
            ],
        )

    r = one(AgentRun(settings, "claude"), handler, False)
    assert r.ok and r.input_tokens == 5


def test_stream_ignores_non_data_lines_and_blank_data(settings):
    body = (
        ": keep-alive\nevent: ping\n\ndata:\n\n"
        'data: {"choices": [{"delta": {"content": "hi"}}]}\n\n'
    )
    r = one(OpenAIChat(settings, "claude"), stream_handler(body), True)
    assert r.ok and r.answer_chars == 2


def test_stream_http_error_records_body_and_no_ttft(settings):
    def handler(request):
        return httpx.Response(503, text="overloaded")

    r = one(OpenAIChat(settings, "claude"), handler, True)
    assert not r.ok and r.status == 503 and r.error == "overloaded" and r.ttft_s is None


def test_malformed_stream_json_is_recorded_not_raised(settings):
    body = sse({"choices": [{"delta": {"content": "ok"}}]}, "{not json")
    r = one(OpenAIChat(settings, "claude"), stream_handler(body), True)
    assert not r.ok and "JSONDecodeError" in r.error
    assert r.ttft_s is not None  # first token had already arrived


def test_malformed_non_stream_json_is_recorded_not_raised(settings):
    def handler(request):
        return httpx.Response(200, content=b"<html>proxy error</html>")

    r = one(OpenAIChat(settings, "claude"), handler, False)
    assert not r.ok and r.status == 200 and "JSONDecodeError" in r.error


def test_timeout_is_recorded_not_raised(settings):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    r = one(OpenAIChat(settings, "gemini"), handler, False)
    assert not r.ok and r.status == 0 and r.error.startswith("ReadTimeout")


def test_connect_error_in_stream_is_recorded_not_raised(settings):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    r = one(OpenAIChat(settings, "gemini"), handler, True)
    assert not r.ok and r.status == 0 and r.error.startswith("ConnectError")


def test_one_failure_does_not_abort_the_batch(settings):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    results, _ = run(
        OpenAIChat(settings, "gemini"), handler, n=3, concurrency=1, stream=False, warmup=0
    )
    assert [r.ok for r in results] == [True, False, True]


def test_error_text_is_truncated(settings):
    def handler(request):
        return httpx.Response(500, text="x" * 2000)

    r = one(OpenAIChat(settings, "gemini"), handler, False)
    assert len(r.error) == 500


def test_prompts_rotate_by_index_and_warmup_indexes_are_negative(settings):
    from agw_harness.settings import PROMPTS

    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    results, _ = run(
        OpenAIChat(settings, "gemini"),
        handler,
        n=len(PROMPTS) + 1,
        concurrency=1,
        stream=False,
        warmup=0,
    )
    assert [r.prompt_id for r in results][-2:] == [len(PROMPTS) - 1, 0]
    assert sent[0] == sent[-1] == PROMPTS[0]


def test_headers_are_fetched_per_request_and_sent(settings):
    tokens = iter(range(100))
    seen = []

    async def headers():
        return {"Authorization": f"Bearer {next(tokens)}"}

    def handler(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await runner.run(
                OpenAIChat(settings, "gemini"),
                headers,
                client=client,
                n=2,
                concurrency=1,
                stream=False,
                warmup=1,
            )

    asyncio.run(go())
    assert seen == ["Bearer 0", "Bearer 1", "Bearer 2"]  # warm-up included


def test_merge_keeps_earlier_values_when_later_event_has_none():
    from agw_harness.protocols import Usage

    merged = runner._merge(Usage(5, None, 2), Usage(None, 7, None))
    assert merged == Usage(5, 7, 2)
    assert runner._merge(Usage(1, 2, 3), None) == Usage(1, 2, 3)


def test_result_to_json_round_trips():
    r = runner.Result(1, 2, 3.0, 200, True, 0.5, None, 1, 2, None, 3, None)
    assert json.loads(r.to_json())["prompt_id"] == 2


def test_stream_error_event_is_recorded_not_counted_ok(settings):
    sse = (
        'data: {"type": "content_block_delta", "delta": {"text": "Bru"}}\n\n'
        'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error"}}\n\n'
    )

    def handler(request):
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    (r,), _ = run(AnthropicNative(settings), handler, n=1, concurrency=1, stream=True, warmup=0)
    assert not r.ok and "overloaded_error" in r.error
    assert r.ttft_s is not None  # the text before the error still arrived


def test_multi_line_sse_data_is_joined_into_one_event(settings):
    sse = 'data: {"choices": [{"delta":\ndata:  {"content": "Brussels."}}]}\n\n'

    def handler(request):
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    (r,), _ = run(
        OpenAIChat(settings, "gemini"), handler, n=1, concurrency=1, stream=True, warmup=0
    )
    assert r.ok and r.answer_chars == len("Brussels.")


def test_unexpected_json_shape_is_recorded_per_request(settings):
    def handler(request):
        return httpx.Response(200, json=["not", "an", "object"])

    results, _ = run(
        OpenAIChat(settings, "gemini"), handler, n=3, concurrency=1, stream=False, warmup=0
    )
    assert len(results) == 3 and all(not r.ok and "AttributeError" in r.error for r in results)


def test_credential_failure_is_recorded_and_not_timed(settings):
    async def broken_headers():
        raise RuntimeError("metadata server unavailable")

    async def go():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200))
        ) as c:
            return await runner.run(
                OpenAIChat(settings, "gemini"),
                broken_headers,
                client=c,
                n=2,
                concurrency=1,
                stream=False,
                warmup=1,
            )

    results, _ = asyncio.run(go())
    assert len(results) == 2
    assert all(
        r.status == 0 and r.latency_s == 0.0 and r.error.startswith("auth:") for r in results
    )


def test_streams_are_requested_uncompressed(settings):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, content=b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\n')

    run(OpenAIChat(settings, "gemini"), handler, n=1, concurrency=1, stream=True, warmup=0)
    assert seen["accept-encoding"] == "identity"


def test_offset_continues_indexes_and_prompt_rotation(settings):
    from agw_harness.settings import PROMPTS

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    results, _ = run(
        OpenAIChat(settings, "gemini"),
        handler,
        n=3,
        concurrency=1,
        stream=False,
        warmup=0,
        offset=25,
    )
    assert [r.index for r in results] == [25, 26, 27]
    assert [r.prompt_id for r in results] == [i % len(PROMPTS) for i in (25, 26, 27)]


HASH = "efa6744af5c504eb73551b191d1f791f2e6ab3f3938829dc580d79fa41f04e83"


def test_redact_replaces_credentials_and_leaves_masked_keys():
    jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJl"  # gitleaks:allow (fake JWT)
    text = (
        f"Rate limit exceeded for api_key: {HASH}. Key=agw-t3 (sk-...gfrA) "
        f"sk-AbCdEfGh1234567890xyz Bearer {jwt} ya29.a0AfB_byC-token"
    )
    out = runner.redact(text)
    for secret in (HASH, "sk-AbCdEfGh1234567890xyz", jwt, "ya29.a0AfB_byC-token"):
        assert secret not in out
    assert "api_key: <sha256 redacted>" in out and "(sk-...gfrA)" in out


def test_clip_error_redacts_before_truncating():
    # A cut through the middle of the hash would leave a fragment that redaction misses.
    text = "x" * 470 + HASH
    out = runner.clip_error(text)
    assert out == "x" * 470 + "<sha256 redacted>"
    assert runner.clip_error(None) is None and runner.clip_error("") == ""


def test_http_error_bodies_are_redacted(settings):
    def handler(request):
        return httpx.Response(429, text=f'{{"error": {{"message": "api_key: {HASH}"}}}}')

    for stream in (False, True):
        r = one(OpenAIChat(settings, "claude"), handler, stream)
        assert r.status == 429 and HASH not in r.error and "<sha256 redacted>" in r.error


def test_stream_error_events_are_redacted_before_the_cut(settings):
    # The hash straddles character 500 of the event's JSON: cutting first would leak a fragment.
    pad = "x" * 430  # the JSON prefix and "api_key: " put the hash at about 463-527
    body = sse({"error": {"message": f"{pad} api_key: {HASH}"}})
    r = one(OpenAIChat(settings, "claude"), stream_handler(body), True)
    assert not r.ok and HASH[:16] not in r.error and "<sha256 redacted>" in r.error


def test_exception_text_is_redacted(settings):
    def handler(request):
        raise httpx.ConnectError(f"refused for key sk-AbCdEfGh1234567890xyz hash {HASH}")

    r = one(OpenAIChat(settings, "gemini"), handler, False)
    assert "sk-AbCdEfGh1234567890xyz" not in r.error and HASH not in r.error


def test_redact_google_api_keys():
    key = "AIza" + "B" * 35
    assert runner.redact(f"key={key}.") == "key=<api key redacted>."
