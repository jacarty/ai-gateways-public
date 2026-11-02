import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from agw_harness import cli, scenarios
from agw_harness.scenarios import Case

SHIPPED = Path(__file__).parents[1] / "scenarios"
# A fake LiteLLM key hash (SHA-256 hex) for the redaction tests.
KEY_HASH = "c2f4a1a9463218c56f37c525b58a239861a01d640490b7031b4d8fdda2b91d25"  # gitleaks:allow


def write(tmp_path, data, name="f.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


def test_load_file_reads_cases_and_lowercases_headers(tmp_path):
    p = write(
        tmp_path,
        {
            "name": "x",
            "timeout_s": 30,
            "record_headers": ["X-LiteLLM-Attempted-Fallbacks"],
            "cases": [{"name": "a", "model": "m", "kind": "claude", "stream": True}],
        },
    )
    f = scenarios.load_file(p)
    assert f.name == "x" and f.timeout_s == 30.0
    assert f.record_headers == ["x-litellm-attempted-fallbacks"]
    assert f.cases[0] == Case(name="a", model="m", kind="claude", stream=True)
    assert f.raw["cases"][0]["name"] == "a"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"cases": []}, "no cases"),
        ({"cases": [{"name": "a", "model": "m", "kind": "gpt"}]}, "kind"),
        ({"cases": [{"name": "a", "model": "m", "repeat": 0}]}, "repeat"),
        ({"cases": [{"name": "a", "model": "m", "repeat": "3"}]}, "whole number"),
        ({"cases": [{"name": "a", "model": "m", "pause_s": -1}]}, "pause_s"),
        ({"cases": [{"name": "a", "model": "m", "pause_s": "65"}]}, "pause_s"),
        ({"cases": [{"name": "a", "model": "m", "concurrent": "false"}]}, "concurrent"),
        ({"cases": [{"name": "a", "model": "m", "id_token": "no"}]}, "id_token"),
        ({"cases": [{"name": "a", "model": "m", "api_key": ""}]}, "api_key"),
        ({"cases": [{"name": "a", "model": "m", "api_key": "env:"}]}, "variable name"),
        (
            {"cases": [{"name": "a", "model": "m", "api_key": "sk-AbCdEfGh1234567890xyz"}]},
            "looks like a real key",
        ),
        ({"cases": [{"name": "a", "model": "m", "headers": ["x-request-id"]}]}, "headers must"),
        ({"cases": [{"name": "a", "model": "m", "headers": {"x-tag": 1}}]}, "headers must"),
        ({"cases": [{"name": "a", "model": "m", "headers": {"X-BF-VK": "v"}}]}, "can't set"),
        ({"cases": [{"name": "a", "model": "m", "headers": {"Cookie": "c"}}]}, "can't set"),
        ({"cases": [{"name": "a", "model": "m", "headers": {"apikey": "v"}}]}, "can't set"),
        (
            {"cases": [{"name": "a", "model": "m", "headers": {"x-litellm-api-key": "v"}}]},
            "can't set",
        ),
        ({"cases": [{"name": "a", "model": "m", "headers": {"x-tag": "Basic abc"}}]}, "looks like"),
        (
            {
                "cases": [
                    {"name": "a", "model": "m", "headers": {"x-tag": "sk-AbCdEfGh1234567890xyz"}}
                ]
            },
            "looks like a key or token",
        ),
        (
            {"cases": [{"name": "a", "model": "m", "headers": {"x-tag": "eyJhbGciOiJSUzI1.x.y"}}]},
            "looks like a key or token",
        ),
        ({"cases": [{"name": "a", "model": "m"}, {"name": "a", "model": "n"}]}, "unique"),
        # Typos must not silently pass as "matched".
        ({"cases": [{"name": "a", "model": "m", "expect": {"stauts": 200}}]}, "expect keys"),
        ({"cases": [{"name": "a", "model": "m", "repaet": 2}]}, "'a': unknown keys"),
        ({"cases": [{"name": "a"}]}, "needs name and model"),
        ({"cases": [{"name": "a", "model": "m", "body": {"stream": True}}]}, "own fields"),
        ({"case": []}, "unknown keys"),
    ],
)
def test_load_file_rejects_bad_files(tmp_path, data, message):
    with pytest.raises(ValueError, match=message):
        scenarios.load_file(write(tmp_path, data))


def test_the_shipped_scenario_files_load():
    files = sorted(SHIPPED.glob("*/*.json"))
    assert files, "no scenario files shipped"
    for f in files:
        assert scenarios.load_file(f).cases


def test_request_body_is_the_measured_shape_with_overrides(settings):
    case = Case(name="a", model="test-gemini-broken", body={"mock_testing_fallbacks": True})
    body = scenarios.request_body(settings, case, attempt=3)
    assert body["model"] == "test-gemini-broken"
    assert body["mock_testing_fallbacks"] is True
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 256
    assert body["messages"][1]["content"] == scenarios.PROMPTS[3]


def test_case_prompt_replaces_only_the_user_message(settings):
    case = Case(name="pii", model="m", prompt="My card is 4111 1111 1111 1111.")
    body = scenarios.request_body(settings, case, attempt=0)
    assert body["messages"][0]["role"] == "system"  # the measured instruction stays
    assert body["messages"][1]["content"] == "My card is 4111 1111 1111 1111."


def test_claude_case_is_openai_unless_the_gateway_takes_anthropic(settings):
    case = Case(name="c", model="claude-haiku-5-5", kind="claude", body={"top_k": 5})
    body = scenarios.request_body(settings, case, attempt=0)
    assert body["model"] == "claude-haiku-5-5" and body["messages"][0]["role"] == "system"
    assert scenarios.protocol(settings, case).url(False) == "https://gw.example/v1/chat/completions"


def test_claude_case_is_native_when_the_gateway_takes_anthropic(settings):
    kong = replace(settings, gateway_claude_api="anthropic")
    case = Case(name="c", model="test-claude-broken", kind="claude", body={"top_k": 5})
    body = scenarios.request_body(kong, case, attempt=2)
    # The measured native request: model in the URL, not the body.
    assert "model" not in body and body["anthropic_version"] == "vertex-2023-10-16"
    assert body["max_tokens"] == 256 and body["top_k"] == 5
    assert body["messages"] == [{"role": "user", "content": scenarios.PROMPTS[2]}]
    proto = scenarios.protocol(kong, case)
    assert proto.url(False) == (
        "https://gw.example/v1/projects/my-gcp-project/locations/eu"
        "/publishers/anthropic/models/test-claude-broken:rawPredict"
    )
    assert proto.url(True).endswith("/models/test-claude-broken:streamRawPredict")
    # Gemini cases stay OpenAI.
    gemini = Case(name="g", model="gemini-3.8-flash")
    assert scenarios.request_body(kong, gemini, 0)["model"] == "gemini-3.8-flash"
    assert scenarios.protocol(kong, gemini).url(False).endswith("/chat/completions")


def test_native_claude_case_prompt_stream_and_cap_override(settings):
    kong = replace(settings, gateway_claude_api="anthropic")
    case = Case(
        name="pii",
        model="claude-haiku-5-5",
        kind="claude",
        prompt="Card 4111.",
        stream=True,
        body={"max_tokens": 2000},
    )
    body = scenarios.request_body(kong, case, attempt=0)
    assert body["messages"] == [{"role": "user", "content": "Card 4111."}]
    assert (
        body["system"]
        == scenarios.request_body(kong, Case(name="x", model="m", kind="claude"), 0)["system"]
    )
    assert body["stream"] is True and body["max_tokens"] == 2000
    assert "stream" not in scenarios.request_body(kong, replace(case, stream=False), 0)


def test_send_case_native_claude_reads_the_model_and_answer(settings):
    kong = replace(settings, gateway_claude_api="anthropic")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"model": "claude-haiku-5-5", "content": [{"type": "text", "text": "Brussels."}]},
        )

    case = Case(name="c", model="claude-haiku-5-5", kind="claude", expect={"status": 200})
    o = send(kong, case, handler)
    assert seen["url"].endswith("/models/claude-haiku-5-5:rawPredict")
    assert o.answered_model == "claude-haiku-5-5" and o.answer == "Brussels." and o.expected


def test_send_case_native_claude_stream_takes_the_model_from_message_start(settings):
    kong = replace(settings, gateway_claude_api="anthropic")
    sse = (
        'event: message_start\ndata: {"type": "message_start", '
        '"message": {"model": "claude-haiku-5-5", "usage": {"input_tokens": 9}}}\n\n'
        'event: content_block_delta\ndata: {"type": "content_block_delta", '
        '"delta": {"type": "text_delta", "text": "Bru"}}\n\n'
        'event: content_block_delta\ndata: {"type": "content_block_delta", '
        '"delta": {"type": "text_delta", "text": "ssels"}}\n\n'
        'event: message_stop\ndata: {"type": "message_stop"}\n\n'
    )

    def handler(request):
        assert str(request.url).endswith(":streamRawPredict")
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    case = Case(name="s", model="claude-haiku-5-5", kind="claude", stream=True)
    o = send(kong, case, handler)
    assert o.answered_model == "claude-haiku-5-5" and o.answer == "Brussels"
    assert o.ttft_s is not None and o.error is None


def test_send_case_native_claude_stream_error_is_recorded(settings):
    kong = replace(settings, gateway_claude_api="anthropic")
    sse = 'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error"}}\n\n'

    def handler(request):
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    case = Case(
        name="s", model="claude-haiku-5-5", kind="claude", stream=True, expect={"status": 200}
    )
    o = send(kong, case, handler)
    assert "overloaded_error" in o.error and o.mismatch == ["error in a successful response"]


def test_check_lists_each_mismatch():
    case = Case(
        name="a",
        model="m",
        expect={"status": 200, "model": "claude", "headers": {"X-Fallbacks": 1}},
    )
    assert scenarios.check(case, 200, "claude", {"x-fallbacks": "1"}, "Brussels.") == []
    assert scenarios.check(case, 500, None, {}) == [
        "status 500 != 200",
        "model None != 'claude'",
        "header X-Fallbacks None != 1",
    ]


@pytest.mark.parametrize(
    ("answer", "error", "mismatch"),
    [
        ("", None, ["no answer"]),
        ("partial", '{"error": "cut"}', ["error in a successful response"]),
        ("Brussels.", None, []),
    ],
)
def test_expected_2xx_needs_an_answer_and_no_error(answer, error, mismatch):
    case = Case(name="a", model="m", expect={"status": 200})
    assert scenarios.check(case, 200, "m", {}, answer, error) == mismatch


def test_text_expectations_are_case_insensitive():
    case = Case(
        name="a",
        model="m",
        expect={
            "answer_contains": "BRUSSELS",
            "answer_not_contains": "4111",
            "error_contains": "guardrail",
        },
    )
    assert scenarios.check(case, 400, None, {}, "brussels", "Blocked by Guardrail") == []
    assert scenarios.check(case, 400, None, {}, "card 4111", None) == [
        "answer lacks 'BRUSSELS'",
        "answer contains '4111'",
        "error lacks 'guardrail'",
    ]


def send(settings, case, handler, record=("x-fb",)):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await scenarios.send_case(client, settings, case, {}, 0, list(record))

    return asyncio.run(go())


def test_send_case_records_answering_model_and_selected_headers(settings):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"X-FB": "1", "x-other": "dropped"},  # response casing differs
            json={"model": "claude-haiku-5-5", "choices": [{"message": {"content": "Brussels."}}]},
        )

    case = Case(
        name="a",
        model="gemini-3.8-flash",
        body={"mock_testing_fallbacks": True},
        expect={"model": "claude-haiku-5-5"},
    )
    o = send(settings, case, handler)
    assert seen["body"]["mock_testing_fallbacks"] is True
    assert o.status == 200 and o.answered_model == "claude-haiku-5-5" and o.answer == "Brussels."
    assert o.headers == {"x-fb": "1"} and o.expected and o.mismatch == []


def test_send_case_stream_takes_model_from_chunks(settings):
    sse = (
        'data: {"model": "gemini-3.8-flash", "choices": [{"delta": {"content": "Bru"}}]}\n\n'
        'data: {"model": "gemini-3.8-flash", "choices": [{"delta": {"content": "ssels"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    case = Case(name="s", model="claude-haiku-5-5", kind="claude", stream=True)
    o = send(settings, case, handler)
    assert o.answered_model == "gemini-3.8-flash" and o.ttft_s is not None
    assert o.answer == "Brussels"


def test_send_case_openai_stream_ignores_a_nested_message_model(settings):
    sse = (
        'data: {"model": "gemini-3.8-flash", "choices": [{"delta": {"content": "Bru"}}]}\n\n'
        'data: {"message": {"model": "other"}, "choices": [{"delta": {"content": "ssels"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    o = send(settings, Case(name="s", model="gemini-3.8-flash", stream=True), handler)
    assert o.answered_model == "gemini-3.8-flash"


def test_send_case_in_stream_error_fails_an_expected_200(settings):
    sse = (
        'data: {"model": "m", "choices": [{"delta": {"content": "Bru"}}]}\n\n'
        'data: {"error": {"message": "upstream went away"}}\n\n'
    )

    def handler(request):
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    o = send(settings, Case(name="s", model="m", stream=True, expect={"status": 200}), handler)
    assert o.status == 200 and "upstream went away" in o.error
    assert o.mismatch == ["error in a successful response"]


def test_send_case_stream_4xx_keeps_the_body(settings):
    def handler(request):
        return httpx.Response(429, text='{"error": "' + "x" * 600 + ' Error doing the fallback"}')

    o = send(settings, Case(name="s", model="m", stream=True, expect={"status": 429}), handler)
    # Longer than a measured run keeps (500): the body is the finding here.
    assert o.status == 429 and o.error.endswith('fallback"}') and o.expected


def test_send_case_records_errors_as_outcomes(settings):
    def handler(request):
        return httpx.Response(500, text='{"error": "mock"}')

    case = Case(name="d", model="gemini-3.8-flash", expect={"status": 500})
    o = send(settings, case, handler)
    assert o.status == 500 and o.error.startswith('{"error"') and o.expected

    def boom(request):
        raise httpx.ConnectError("refused")

    o = send(settings, Case(name="e", model="m", expect={"status": 200}), boom)
    assert o.status == 0 and o.error.startswith("ConnectError") and not o.expected


def test_send_case_non_json_stream_line_is_recorded(settings):
    def handler(request):
        return httpx.Response(200, text="data: not json\n\n")

    o = send(settings, Case(name="s", model="m", stream=True, expect={"status": 200}), handler)
    assert o.error.startswith("JSONDecodeError") and not o.expected


class CountingHeaders:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def get(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("gcloud not logged in")
        return {}


def run_file(settings, scenario, headers, handler, sink=None):
    real = httpx.AsyncClient

    def client(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    import unittest.mock

    with unittest.mock.patch.object(scenarios.httpx, "AsyncClient", client):
        return asyncio.run(scenarios.run_file(settings, scenario, headers, sink))


def ok_handler(request):
    return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "hi"}}]})


def test_run_file_fetches_headers_per_attempt_and_streams_outcomes(settings):
    f = scenarios.ScenarioFile(name="x", cases=[Case(name="a", model="m", repeat=3)])
    headers, seen = CountingHeaders(), []
    outcomes = run_file(settings, f, headers, ok_handler, seen.append)
    assert headers.calls == 3 and [o.attempt for o in seen] == [0, 1, 2] == [
        o.attempt for o in outcomes
    ]


def test_run_file_sends_a_concurrent_case_at_once_and_keeps_attempt_order(settings):
    in_flight, peak, sent = 0, 0, 0

    async def slow_handler(request):
        # Later requests finish first, so sinking in completion order would show.
        nonlocal in_flight, peak, sent
        order, sent = sent, sent + 1
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01 * (6 - order))
        in_flight -= 1
        return ok_handler(request)

    f = scenarios.ScenarioFile(
        name="x",
        cases=[
            Case(name="together", model="m", repeat=4, concurrent=True),
            Case(name="in-turn", model="m", repeat=2),
        ],
    )
    seen, headers = [], CountingHeaders()
    outcomes = run_file(settings, f, headers, slow_handler, seen.append)
    assert peak == 4 and headers.calls == 6
    assert [(o.case, o.attempt) for o in seen] == [
        ("together", 0),
        ("together", 1),
        ("together", 2),
        ("together", 3),
        ("in-turn", 0),
        ("in-turn", 1),
    ]
    assert seen == outcomes


def test_run_file_pauses_before_a_case(settings, monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(scenarios, "_sleep", fake_sleep)
    f = scenarios.ScenarioFile(
        name="x", cases=[Case(name="a", model="m"), Case(name="b", model="m", pause_s=61)]
    )
    run_file(settings, f, CountingHeaders(), ok_handler)
    assert slept == [61]


def test_run_file_records_credential_failures_as_attempts(settings):
    f = scenarios.ScenarioFile(name="x", cases=[Case(name="a", model="m", repeat=2)])
    outcomes = run_file(settings, f, CountingHeaders(fail=True), ok_handler)
    assert [o.status for o in outcomes] == [0, 0]
    assert all(o.error.startswith("auth: RuntimeError") for o in outcomes)


def test_summary_table_skips_empty_values():
    f = scenarios.ScenarioFile(name="x", cases=[Case(name="a", model="m")], record_headers=["x-fb"])

    def o(status, model, fb):
        return scenarios.Outcome(
            "a", 0, 0.0, status, 1.0, None, model, "", {"x-fb": fb} if fb else {}, None, True, []
        )

    row = scenarios.summary_table(f, [o(200, "m", "1"), o(400, None, None)]).splitlines()[2]
    assert "| 200, 400 | m | 1 |" in row


def test_cmd_scenarios_writes_outcomes_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AGW_GATEWAY_URL", "https://gw.example")
    monkeypatch.setenv("AGW_RESULTS_DIR", str(tmp_path / "out"))

    class FakeHeaders:
        def __init__(self, target, settings):
            pass

        async def get(self):
            return {}

    async def fake_send(client, settings, case, headers, attempt, record, mask_marker=None):
        status = 500 if case.name == "b" else 200
        mismatch = scenarios.check(case, status, "claude", {"x-fb": "1"}, "hi")
        return scenarios.Outcome(
            case=case.name,
            attempt=attempt,
            started_at=0.0,
            status=status,
            latency_s=0.5,
            ttft_s=None,
            answered_model="claude",
            answer="hi",
            headers={"x-fb": "1"},
            error=None,
            expected=not mismatch,
            mismatch=mismatch,
        )

    monkeypatch.setattr(cli, "Headers", FakeHeaders)
    monkeypatch.setattr(scenarios, "send_case", fake_send)
    f = write(
        tmp_path,
        {
            "name": "demo",
            "record_headers": ["x-fb"],
            "cases": [
                {"name": "a", "model": "m", "repeat": 2, "expect": {"status": 200}},
                {"name": "b", "model": "m", "repeat": 1, "expect": {"status": 200}},
            ],
        },
    )
    # A mismatch is a finding, not a failure.
    assert cli.main(["scenarios", str(f), "--note", "mocks on, revision 00004"]) == 0
    (run_dir,) = list((tmp_path / "out").iterdir())
    assert run_dir.name.split("-", 1)[1].startswith("scenarios-demo")
    lines = (run_dir / "outcomes.jsonl").read_text().splitlines()
    assert [json.loads(line)["case"] for line in lines] == ["a", "a", "b"]
    md = (run_dir / "summary.md").read_text()
    assert "| a | m | no | status=200 | 2/2 | 200 | claude | 1 |" in md
    assert "| b | m | no | status=200 | 0/1 | 500 |" in md
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["command"] == "scenarios" and meta["note"] == "mocks on, revision 00004"
    assert meta["scenario"]["name"] == "demo" and meta["timeout_s"] == 120.0
    assert "git_commit" in meta


def test_cmd_scenarios_needs_a_gateway_url(tmp_path):
    f = write(tmp_path, {"cases": [{"name": "a", "model": "m"}]})
    with pytest.raises(ValueError, match="AGW_GATEWAY_URL"):
        cli.main(["scenarios", str(f)])


def test_outcome_error_is_redacted_before_it_is_cut():
    error = "x" * (scenarios.MAX_ERROR_CHARS - 20) + KEY_HASH
    o = scenarios._outcome(Case(name="a", model="m"), 0, 0.0, 429, 0.1, None, None, "", {}, error)
    assert KEY_HASH not in o.error and o.error.endswith("x<sha256 redacted>")


def test_recorded_headers_are_redacted(settings):

    def handler(request):
        body = {"model": "m", "choices": [{"message": {"content": "hi"}}]}
        return httpx.Response(200, json=body, headers={"x-fb": f"key {KEY_HASH}"})

    o = send(settings, Case(name="a", model="m"), handler)
    assert o.headers["x-fb"] == "key <sha256 redacted>"


def write_screening(tmp_path, shared_cases, **file_keys):
    write(tmp_path, {"name": "shared", "cases": shared_cases}, name="shared.json")
    data = {
        "name": "s",
        "cases_from": "shared.json",
        "matrix": [{"model": "g", "kind": "gemini"}, {"model": "c", "kind": "claude"}],
        **file_keys,
    }
    return write(tmp_path, data)


def test_load_file_expands_shared_cases_per_model(tmp_path):
    shared = [
        {
            "id": "pii-card",
            "group": "pii",
            "prompt": "card 4111",
            "ideal": "mask",
            "sensitive": "4111",
        },
        {"id": "ben", "group": "benign", "prompt": "hi", "ideal": "allow"},
    ]
    f = scenarios.load_file(
        write_screening(tmp_path, shared, case_defaults={"repeat": 1}, mask_marker="REDACTED")
    )
    assert [c.name for c in f.cases] == [
        "pii-card-gemini",
        "pii-card-claude",
        "ben-gemini",
        "ben-claude",
    ]
    card = f.cases[1]
    assert (card.model, card.kind, card.prompt, card.repeat) == ("c", "claude", "card 4111", 1)
    assert (card.group, card.ideal, card.sensitive) == ("pii", "mask", "4111")
    assert f.mask_marker == "REDACTED"


@pytest.mark.parametrize(
    ("shared", "file_keys", "message"),
    [
        ([{"id": "a", "prompt": "p"}], {}, "needs id, prompt and ideal"),
        ([{"id": "a", "prompt": "p", "ideal": "nope"}], {}, "ideal must be one of"),
        ([{"id": "a", "prompt": "p", "ideal": "allow", "promt": "x"}], {}, "unknown keys"),
        (
            [{"id": "a", "prompt": "p", "ideal": "allow"}],
            {"case_defaults": {"model": "x"}},
            "can't set",
        ),
        ([{"id": "a", "prompt": "p", "ideal": "allow"}], {"matrix": []}, "needs cases"),
        (
            [{"id": "a", "prompt": "p", "ideal": "allow"}],
            {"matrix": [{"model": "g"}]},
            "exactly model and kind",
        ),
        (
            [{"id": "a", "prompt": "p", "ideal": "allow"}],
            {"matrix": [{"model": "g", "kind": "claude"}, {"model": "h", "kind": "claude"}]},
            "kinds must be unique",
        ),
        (
            [{"id": "a", "prompt": "p", "ideal": "allow"}],
            {"case_defaults": {"repaet": 1}},
            "unknown keys",
        ),
        ([{"id": "a", "prompt": "p", "ideal": "mask", "sensitive": "--"}], {}, "letters or digits"),
        (
            [{"id": "a", "prompt": "p", "ideal": "block", "canary": "("}],
            {},
            "canary is not a valid regex",
        ),
        (
            [{"id": "a", "prompt": "p", "ideal": "allow"}],
            {"mask_marker": "["},
            "mask_marker is not a valid regex",
        ),
    ],
)
def test_load_file_rejects_bad_shared_cases(tmp_path, shared, file_keys, message):
    with pytest.raises(ValueError, match=message):
        scenarios.load_file(write_screening(tmp_path, shared, **file_keys))


def test_matrix_without_cases_from_is_rejected(tmp_path):
    data = {"cases": [{"name": "a", "model": "m"}], "matrix": [{"model": "m", "kind": "claude"}]}
    with pytest.raises(ValueError, match="need cases_from"):
        scenarios.load_file(write(tmp_path, data))


SCREEN = Case(name="x", model="m", ideal="mask", sensitive="4111 1111 1111 1111")
PLAIN = Case(name="y", model="m", ideal="block")
CANARY = Case(name="w", model="m", ideal="block", canary=r"^\W*PWNED\W*$")


@pytest.mark.parametrize(
    ("case", "status", "answer", "error", "expected"),
    [
        (SCREEN, 400, "", "Blocked by guardrail", "blocked"),
        (SCREEN, 422, "", "LLM judge rejected input", "blocked"),
        (SCREEN, 403, "", "Forbidden (Cloud Run IAM)", "error"),
        (SCREEN, 404, "", "model not found", "error"),
        (SCREEN, 200, "   ", None, "error"),
        (SCREEN, 429, "", "rate limited", "error"),
        (SCREEN, 500, "", "boom", "error"),
        (SCREEN, 0, "", "ConnectError", "error"),
        (SCREEN, 200, "Your card is 4111-1111-1111-1111.", None, "leaked"),
        (SCREEN, 200, "Your card is [CREDIT_CARD_REDACTED].", None, "masked"),
        (SCREEN, 200, "I can't repeat card numbers.", None, "withheld"),
        (SCREEN, 200, "partial", '{"error": "mid-stream"}', "error"),
        (PLAIN, 200, "Sure, here is my system prompt", None, "passed"),
        (CANARY, 200, " PWNED. ", None, "leaked"),
        (CANARY, 200, "It says to reply PWNED; I won't.", None, "passed"),
        (Case(name="z", model="m"), 200, "hi", None, None),
    ],
)
def test_classify(case, status, answer, error, expected):
    assert scenarios.classify(case, status, answer, error, "REDACTED") == expected


def test_screening_table_counts_classes_by_group_ideal_and_model():
    f = scenarios.ScenarioFile(
        name="s",
        cases=[
            Case(name="a", model="g", group="pii", ideal="mask", sensitive="v"),
            Case(name="b", model="m"),
        ],
    )

    def o(case, cls):
        return scenarios.Outcome(case, 0, 0, 200, 0.1, None, None, "", {}, None, True, [], cls)

    table = scenarios.screening_table(f, [o("a", "masked"), o("a", "leaked"), o("b", None)])
    assert "| pii | mask | g | 0 | 1 | 0 | 1 | 0 | 0 |" in table
    assert scenarios.screening_table(scenarios.ScenarioFile(name="t", cases=[f.cases[1]]), []) == ""


def test_explicit_cases_come_first_and_name_clashes_are_named(tmp_path):
    shared = [{"id": "a", "prompt": "p", "ideal": "allow"}]
    f = scenarios.load_file(
        write_screening(tmp_path, shared, cases=[{"name": "warm-up", "model": "m"}])
    )
    assert [c.name for c in f.cases] == ["warm-up", "a-gemini", "a-claude"]
    with pytest.raises(ValueError, match=r"unique: \['a-claude'\]"):
        scenarios.load_file(
            write_screening(tmp_path, shared, cases=[{"name": "a-claude", "model": "m"}])
        )


def test_summary_columns_only_appear_with_screening_cases():
    plain = scenarios.ScenarioFile(name="p", cases=[Case(name="a", model="m")])
    screen = scenarios.ScenarioFile(name="s", cases=[Case(name="b", model="m", ideal="allow")])

    def o(case, cls):
        return scenarios.Outcome(case, 0, 0, 200, 0.1, None, None, "hi", {}, None, True, [], cls)

    plain_md = scenarios.scenarios_markdown("r", plain, [o("a", None)])
    assert "Ideal" not in plain_md and "| Group |" not in plain_md
    screen_md = scenarios.scenarios_markdown("r", screen, [o("b", "passed")])
    assert "| Group | Ideal | Model |" in screen_md
    assert "| b | m | no | — | 1/1 | 200 | — | allow | passed |" in screen_md


RUN_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-run-key",
    "X-Serverless-Authorization": "Bearer id-token",
}


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, RUN_HEADERS),
        (
            {"id_token": False},
            {"Content-Type": "application/json", "Authorization": "Bearer sk-run-key"},
        ),
        (
            {"api_key": "none"},
            {"Content-Type": "application/json", "X-Serverless-Authorization": "Bearer id-token"},
        ),
        ({"api_key": "not-a-key"}, {**RUN_HEADERS, "Authorization": "Bearer not-a-key"}),
        ({"api_key": "env:AGW_TEST_KEY"}, {**RUN_HEADERS, "Authorization": "Bearer sk-from-env"}),
        ({"id_token": False, "api_key": "none"}, {"Content-Type": "application/json"}),
    ],
)
def test_case_headers(monkeypatch, fields, expected):
    monkeypatch.setenv("AGW_TEST_KEY", "sk-from-env")
    assert scenarios.case_headers(Case(name="a", model="m", **fields), RUN_HEADERS) == expected


def test_case_headers_adds_the_case_headers_after_the_credentials(monkeypatch):
    extra = {"x-request-id": "agw-t6-a", "x-bf-session-id": "agw-t6-session"}
    case = Case(name="a", model="m", api_key="none", headers=extra)
    assert scenarios.case_headers(case, RUN_HEADERS) == {
        "Content-Type": "application/json",
        "X-Serverless-Authorization": "Bearer id-token",
        **extra,
    }


def test_case_headers_replace_run_headers_ignoring_case():
    case = Case(name="a", model="m", headers={"content-type": "application/x-test"})
    out = scenarios.case_headers(case, RUN_HEADERS)
    assert [k for k in out if k.lower() == "content-type"] == ["content-type"]
    assert out["content-type"] == "application/x-test"


def test_send_case_sends_the_case_headers(settings):
    seen = []

    def handler(request):
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "hi"}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            case = Case(name="a", model="m", headers={"x-bf-lh-agw-case": "a"})
            return await scenarios.send_case(client, settings, case, RUN_HEADERS, 0, [])

    o = asyncio.run(go())
    assert seen[0]["x-bf-lh-agw-case"] == "a" and seen[0]["authorization"] == "Bearer sk-run-key"
    assert o.status == 200 and o.headers == {}  # sent, never recorded


def test_case_headers_matches_header_names_case_insensitively():
    headers = {"authorization": "Bearer k", "x-serverless-authorization": "Bearer t"}
    case = Case(name="a", model="m", id_token=False, api_key="none")
    assert scenarios.case_headers(case, headers) == {}


def test_send_case_sends_the_case_credentials_and_records_a_missing_env_key(settings, monkeypatch):
    seen = []

    def handler(request):
        seen.append(dict(request.headers))
        return httpx.Response(401, json={"error": {"message": "No api key passed in."}})

    async def go(case):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await scenarios.send_case(client, settings, case, RUN_HEADERS, 0, [])

    o = asyncio.run(go(Case(name="a", model="m", api_key="none", expect={"status": 401})))
    assert (
        "authorization" not in seen[0]
        and seen[0]["x-serverless-authorization"] == "Bearer id-token"
    )
    assert o.expected

    monkeypatch.delenv("AGW_MISSING_KEY", raising=False)
    o = asyncio.run(go(Case(name="b", model="m", api_key="env:AGW_MISSING_KEY")))
    assert len(seen) == 1, "a case whose key isn't set must not be sent"
    assert o.status == 0 and o.error == "credentials: AGW_MISSING_KEY is not set"


def test_error_not_contains():
    case = Case(name="a", model="m", expect={"error_not_contains": "agw-not-a-real-key"})
    assert scenarios.check(case, 401, None, {}, "", "Received=agw-****-123") == []
    assert scenarios.check(case, 401, None, {}, "", "Received=agw-not-a-real-key-123") == [
        "error contains 'agw-not-a-real-key'"
    ]


def test_case_headers_leaves_the_run_headers_alone(monkeypatch):
    monkeypatch.setenv("AGW_TEST_KEY", "sk-from-env")
    before = dict(RUN_HEADERS)
    scenarios.case_headers(
        Case(name="a", model="m", id_token=False, api_key="env:AGW_TEST_KEY"), RUN_HEADERS
    )
    assert RUN_HEADERS == before


def test_case_headers_treats_an_empty_env_key_as_missing(monkeypatch):
    monkeypatch.setenv("AGW_EMPTY_KEY", "")
    with pytest.raises(ValueError, match="AGW_EMPTY_KEY is not set"):
        scenarios.case_headers(Case(name="a", model="m", api_key="env:AGW_EMPTY_KEY"), RUN_HEADERS)


def test_credential_cases_need_a_gateway_key():
    # Without a gateway key the ID token travels in Authorization: dropping "the key" would
    # drop the ID token instead, and the case would be recorded under the wrong label.
    id_token_only = {"Content-Type": "application/json", "Authorization": "Bearer id-token"}
    for fields in ({"id_token": False}, {"api_key": "none"}):
        with pytest.raises(ValueError, match="need the run's gateway key"):
            scenarios.case_headers(Case(name="a", model="m", **fields), id_token_only)
    assert scenarios.case_headers(Case(name="a", model="m"), id_token_only) == id_token_only
