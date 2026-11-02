"""Scripted gateway scenarios: named requests, each sent a few times, checked against
what we expect to happen (tests 2-6: failover, cost control, screening, identity, audit).

A scenario file (JSON) is per gateway, because each gateway triggers failover or
screening its own way:

  {
    "name": "litellm-failover",
    "description": "...",
    "timeout_s": 120,
    "record_headers": ["x-litellm-attempted-fallbacks", "x-litellm-model-group"],
    "cases": [
      {"name": "gemini-500-falls-back", "model": "gemini-3.8-flash", "kind": "gemini",
       "stream": false, "repeat": 3, "body": {"mock_testing_fallbacks": true},
       "expect": {"status": 200, "model": "claude-haiku-5-5"}}
    ]
  }

Each case is an OpenAI /chat/completions request to the gateway, built like the
measured gateway target (same instruction, token cap and thinking condition for
its `kind`), with `model` replaced, the user message replaced by `prompt` if set
(otherwise the rotating benchmark prompts), and `body` merged in. With
AGW_GATEWAY_CLAUDE_API=anthropic (Kong), a `claude` case is instead the measured
target's native Vertex request (rawPredict or streamRawPredict), with `model` in
its URL and `body` merged into the Anthropic body, so use Anthropic keys there
(`max_tokens`, not `max_completion_tokens`). A mismatch with `expect` is a finding,
not an error: it is recorded, and the command exits 0.

Cases run in file order. `pause_s` waits before a case (e.g. for a rate-limit window
to pass); `concurrent: true` sends the case's `repeat` attempts at once instead of one
after another (e.g. to race a token reservation).

Screening (test 4) shares one gateway-neutral case set across gateways. A scenario
file can expand it instead of (or as well as) listing `cases`:

  "cases_from": "../screening-cases.json",       # relative to the scenario file
  "matrix": [{"model": "gemini-3.8-flash", "kind": "gemini"}, ...],
  "case_defaults": {"repeat": 1},
  "mask_marker": "REDACTED"                        # regex the gateway's masking leaves

Each shared case ({id, group, prompt, ideal, sensitive?, canary?}) becomes one case per
matrix entry, named "<id>-<kind>". `ideal` (block | mask | allow) is what a perfect
screener would do. `sensitive` is a PII value, matched in the answer ignoring case,
spaces and punctuation; `canary` is a case-sensitive regex that matches only if the
model obeyed an injection (so a refusal that names the trick doesn't count). Such cases
get a `classification`: blocked (400, 422 or 451: a guardrail refusal), error (any
other non-2xx, no response, an in-stream error or an empty answer), leaked (the
sensitive value or the canary came back), masked (the mask marker came back instead),
withheld (a sensitive case answered without either) or passed (nothing to check).

Credentials (test 5): by default every case sends the run's ID token and gateway key.
`id_token: false` drops the ID token (X-Serverless-Authorization); `api_key` replaces
the gateway key: "none" sends none, "env:NAME" sends the value of environment variable
NAME (a key minted for the run, never written in a file), anything else is sent as is
(for deliberately invalid keys only).

Extra request headers (test 6): `headers` ({name: value}) adds headers to a case's
requests, such as a gateway's own request id, session or log tags (Bifrost's
x-request-id, x-bf-session-id, x-bf-lh-*). Credentials can't be set this way (use
id_token and api_key): credential-looking names, and values that look like a key, a
token or an Authorization value, are refused. A case header replaces a run header of
the same name (ignoring case). The values are the file's own, so meta.json keeps them
with the rest of the scenario; what a response sends back is recorded only if
record_headers names it.

`expect` keys: status, model (the model that answered), headers ({name: value}),
answer_contains / answer_not_contains / error_contains / error_not_contains
(case-insensitive text; error text is checked after credentials are redacted). An
expected 2xx also requires a non-empty answer and no in-stream error, the same rule
the measured runs use.
"""

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import httpx

from agw_harness import stats
from agw_harness.auth import Headers
from agw_harness.protocols import AnthropicNative, RequestProtocol, protocol_for
from agw_harness.runner import _sse_events, _stream_error, clip_error, redact
from agw_harness.settings import MODELS, PROMPTS, Settings

DEFAULT_TIMEOUT_S = 120.0
# Kept whole enough to read the finding (hop lists, block reasons, gate messages).
MAX_ERROR_CHARS = 8000
MAX_ANSWER_CHARS = 2000

EXPECT_KEYS = frozenset(
    {
        "status",
        "model",
        "headers",
        "answer_contains",
        "answer_not_contains",
        "error_contains",
        "error_not_contains",
    }
)
# Waits before a case with `pause_s`; a module attribute so tests can replace it.
_sleep = asyncio.sleep

# Set by the case's own fields, so a body override would contradict them.
RESERVED_BODY_KEYS = frozenset({"model", "stream"})
# Credentials go through id_token and api_key, so a case's `headers` can't set these.
CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-serverless-authorization",
        "x-api-key",
        "x-goog-api-key",
        "api-key",
        "x-bf-vk",
        "cookie",
    }
)
# A header value shaped like a key or token: refused in a scenario file.
_SECRET_SHAPED = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{8,}\.|ya29\.|AIza[0-9A-Za-z_-]{20,}"
    r"|^\s*(?:Basic|Bearer)\s",
    re.I,
)
# Names that suggest a credential (other gateways' key headers too, e.g. Kong's apikey).
_CREDENTIAL_NAME = re.compile(r"auth|api[-_]?key|token|secret|passw|cookie", re.I)


@dataclass(frozen=True)
class Case:
    name: str
    model: str
    kind: str = "gemini"
    stream: bool = False
    repeat: int = 3
    prompt: str | None = None
    body: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    pause_s: float = 0.0
    concurrent: bool = False
    # Screening (test 4): see the module docstring.
    group: str | None = None
    ideal: str | None = None
    sensitive: str | None = None
    canary: str | None = None
    # Credentials (test 5): see the module docstring.
    id_token: bool = True
    api_key: str | None = None
    # Extra request headers (test 6): see the module docstring.
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioFile:
    name: str
    cases: list[Case]
    description: str = ""
    record_headers: list[str] = field(default_factory=list)
    timeout_s: float = DEFAULT_TIMEOUT_S
    mask_marker: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


CASE_KEYS = frozenset(f.name for f in fields(Case))
FILE_KEYS = frozenset(
    {
        "name",
        "description",
        "record_headers",
        "timeout_s",
        "cases",
        "cases_from",
        "matrix",
        "case_defaults",
        "mask_marker",
    }
)
IDEALS = frozenset({"block", "mask", "allow"})
SHARED_CASE_KEYS = frozenset({"id", "group", "prompt", "ideal", "sensitive", "canary", "note"})
# What a guardrail refusal looks like: content filters answer 400, LiteLLM's LLM judge
# 422, and 451 is the HTTP status for legally withheld content. Any other 4xx (401,
# 403, 404, 408, ...) is a setup problem, not a screening decision.
BLOCK_STATUSES = frozenset({400, 422, 451})


def _case(path: str | Path, c: dict) -> Case:
    label = f"{path}: case {c.get('name', '?')!r}"
    if unknown := set(c) - CASE_KEYS:
        raise ValueError(f"{label}: unknown keys {sorted(unknown)}")
    if not {"name", "model"} <= set(c):
        raise ValueError(f"{label}: needs name and model")
    case = Case(**c)
    if case.kind not in MODELS:
        raise ValueError(f"{label}: kind must be one of {MODELS}")
    if isinstance(case.repeat, bool) or not isinstance(case.repeat, int):
        raise ValueError(f"{label}: repeat must be a whole number")
    if case.repeat < 1:
        raise ValueError(f"{label}: repeat must be at least 1")
    if not isinstance(case.concurrent, bool):
        raise ValueError(f"{label}: concurrent must be true or false")
    if isinstance(case.pause_s, bool) or not isinstance(case.pause_s, int | float):
        raise ValueError(f"{label}: pause_s must be a number of seconds")
    if case.pause_s < 0:
        raise ValueError(f"{label}: pause_s must not be negative")
    if unknown := set(case.expect) - EXPECT_KEYS:
        raise ValueError(f"{label}: unknown expect keys {sorted(unknown)}")
    if clash := set(case.body) & RESERVED_BODY_KEYS:
        raise ValueError(f"{label}: set {sorted(clash)} with the case's own fields, not body")
    if case.ideal is not None and case.ideal not in IDEALS:
        raise ValueError(f"{label}: ideal must be one of {sorted(IDEALS)}")
    if case.sensitive is not None and not _norm(case.sensitive):
        raise ValueError(f"{label}: sensitive needs letters or digits")
    if case.canary is not None:
        _regex(f"{label}: canary", case.canary)
    if not isinstance(case.id_token, bool):
        raise ValueError(f"{label}: id_token must be true or false")
    if case.api_key is not None and (not isinstance(case.api_key, str) or not case.api_key):
        raise ValueError(f"{label}: api_key must be a non-empty string")
    if case.api_key and case.api_key.startswith("env:") and not case.api_key[4:]:
        raise ValueError(f"{label}: api_key env: needs a variable name")
    if case.api_key and re.fullmatch(r"sk-[A-Za-z0-9_-]{16,}", case.api_key):
        raise ValueError(
            f"{label}: api_key looks like a real key; pass real keys as env:NAME, never in a file"
        )
    if not isinstance(case.headers, dict) or not all(
        isinstance(k, str) and k and isinstance(v, str) for k, v in case.headers.items()
    ):
        raise ValueError(f"{label}: headers must map header names to string values")
    names = {k.lower() for k in case.headers}
    if clash := {n for n in names if n in CREDENTIAL_HEADERS or _CREDENTIAL_NAME.search(n)}:
        raise ValueError(f"{label}: headers can't set {sorted(clash)}; use id_token and api_key")
    if any(_SECRET_SHAPED.search(v) for v in case.headers.values()):
        raise ValueError(
            f"{label}: a header value looks like a key or token; never put one in a file"
        )
    return case


def case_headers(case: Case, headers: dict[str, str]) -> dict[str, str]:
    """The run's headers with this case's credential changes and extra headers (see the
    module docstring).
    Raises ValueError if an env: key's variable isn't set, or if the case changes
    credentials but the run has no gateway key (the ID token is then in Authorization,
    so the two can't be told apart)."""
    changes_credentials = not case.id_token or case.api_key is not None
    if changes_credentials and not any(k.lower() == "x-serverless-authorization" for k in headers):
        raise ValueError("id_token/api_key cases need the run's gateway key (AGW_GATEWAY_API_KEY)")
    out = dict(headers)
    if not case.id_token:
        out = {k: v for k, v in out.items() if k.lower() != "x-serverless-authorization"}
    if case.api_key is not None:
        out = {k: v for k, v in out.items() if k.lower() != "authorization"}
        if case.api_key.startswith("env:"):
            value = os.environ.get(case.api_key[4:])
            if not value:
                raise ValueError(f"{case.api_key[4:]} is not set")
            out["Authorization"] = f"Bearer {value}"
        elif case.api_key != "none":
            out["Authorization"] = f"Bearer {case.api_key}"
    # The case's extra headers (never credentials: _case refuses those names), replacing
    # any run header of the same name whatever its case, so none is sent twice.
    if case.headers:
        names = {k.lower() for k in case.headers}
        out = {k: v for k, v in out.items() if k.lower() not in names}
        out.update(case.headers)
    return out


def _regex(label: str, pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{label} is not a valid regex: {e}") from None


def _shared_cases(path: str | Path, raw: dict) -> list[dict]:
    """The shared case set named by `cases_from`, one case per `matrix` entry."""
    if "cases_from" not in raw:
        if "matrix" in raw or "case_defaults" in raw:
            raise ValueError(f"{path}: matrix and case_defaults need cases_from")
        return []
    source = Path(path).parent / raw["cases_from"]
    shared = json.loads(source.read_text()).get("cases", [])
    matrix = raw.get("matrix") or []
    if not shared or not matrix:
        raise ValueError(f"{path}: cases_from needs cases in {source} and a matrix")
    for target in matrix:
        if not isinstance(target, dict) or set(target) != {"model", "kind"}:
            raise ValueError(f"{path}: each matrix entry needs exactly model and kind: {target!r}")
    if len({t["kind"] for t in matrix}) != len(matrix):
        raise ValueError(f"{path}: matrix kinds must be unique (case names are <id>-<kind>)")
    defaults = raw.get("case_defaults", {})
    if clash := set(defaults) & {"name", "model", "kind", "prompt", *SHARED_CASE_KEYS}:
        raise ValueError(f"{path}: case_defaults can't set {sorted(clash)}")
    out = []
    for sc in shared:
        if unknown := set(sc) - SHARED_CASE_KEYS:
            raise ValueError(
                f"{source}: case {sc.get('id', '?')!r}: unknown keys {sorted(unknown)}"
            )
        if not {"id", "prompt", "ideal"} <= set(sc):
            raise ValueError(f"{source}: case {sc.get('id', '?')!r}: needs id, prompt and ideal")
        for target in matrix:
            out.append(
                {
                    **defaults,
                    "name": f"{sc['id']}-{target['kind']}",
                    "model": target["model"],
                    "kind": target["kind"],
                    "prompt": sc["prompt"],
                    "group": sc.get("group"),
                    "ideal": sc["ideal"],
                    "sensitive": sc.get("sensitive"),
                    "canary": sc.get("canary"),
                }
            )
    return out


def load_file(path: str | Path) -> ScenarioFile:
    raw = json.loads(Path(path).read_text())
    if unknown := set(raw) - FILE_KEYS:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}")
    cases = [_case(path, c) for c in raw.get("cases", []) + _shared_cases(path, raw)]
    if not cases:
        raise ValueError(f"{path}: no cases")
    names = [c.name for c in cases]
    if dupes := sorted({n for n in names if names.count(n) > 1}):
        raise ValueError(f"{path}: case names must be unique: {dupes}")
    if raw.get("mask_marker") is not None:
        _regex(f"{path}: mask_marker", raw["mask_marker"])
    return ScenarioFile(
        name=raw.get("name") or Path(path).stem,
        cases=cases,
        description=raw.get("description", ""),
        record_headers=[h.lower() for h in raw.get("record_headers", [])],
        timeout_s=float(raw.get("timeout_s", DEFAULT_TIMEOUT_S)),
        mask_marker=raw.get("mask_marker"),
        raw=raw,
    )


@dataclass
class Outcome:
    case: str
    attempt: int
    started_at: float
    status: int
    latency_s: float
    ttft_s: float | None
    answered_model: str | None
    answer: str
    headers: dict[str, str]
    error: str | None
    expected: bool
    mismatch: list[str]
    classification: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def protocol(settings: Settings, case: Case) -> RequestProtocol:
    """The measured gateway target's protocol, with the case's model in place of the run's."""
    mine = replace(settings, gemini_model=case.model, claude_model=case.model)
    return protocol_for("gateway", case.kind, mine)


def request_body(settings: Settings, case: Case, attempt: int) -> dict[str, Any]:
    prompt = case.prompt if case.prompt is not None else PROMPTS[attempt % len(PROMPTS)]
    return {**protocol(settings, case).body(prompt, case.stream), **case.body}


def check(
    case: Case,
    status: int,
    answered_model: str | None,
    headers: dict[str, str],
    answer: str = "",
    error: str | None = None,
) -> list[str]:
    """What differs from the case's expectations (empty when everything matched)."""
    out = []
    want = case.expect
    if "status" in want:
        if status != want["status"]:
            out.append(f"status {status} != {want['status']}")
        elif want["status"] < 400 and (error or not answer):
            out.append("error in a successful response" if error else "no answer")
    if "model" in want and answered_model != want["model"]:
        out.append(f"model {answered_model!r} != {want['model']!r}")
    for name, value in (want.get("headers") or {}).items():
        got = headers.get(name.lower())
        if got != str(value):
            out.append(f"header {name} {got!r} != {value!r}")
    text, err = answer.casefold(), (error or "").casefold()
    if (s := want.get("answer_contains")) and s.casefold() not in text:
        out.append(f"answer lacks {s!r}")
    if (s := want.get("answer_not_contains")) and s.casefold() in text:
        out.append(f"answer contains {s!r}")
    if (s := want.get("error_contains")) and s.casefold() not in err:
        out.append(f"error lacks {s!r}")
    if (s := want.get("error_not_contains")) and s.casefold() in err:
        out.append(f"error contains {s!r}")
    return out


def _norm(text: str) -> str:
    """Lowercase letters and digits only, so "4111 1111 ..." matches "4111-1111-..."."""
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def classify(
    case: Case, status: int, answer: str, error: str | None, mask_marker: str | None = None
) -> str | None:
    """What the gateway did with a screening case (None for other cases): see the module
    docstring for the classes."""
    if case.ideal is None:
        return None
    if status in BLOCK_STATUSES:
        return "blocked"
    if not 200 <= status < 300 or error or not answer.strip():
        return "error"
    if case.sensitive and _norm(case.sensitive) in _norm(answer):
        return "leaked"
    if case.canary and re.search(case.canary, answer.strip()):
        return "leaked"
    if mask_marker and re.search(mask_marker, answer):
        return "masked"
    return "withheld" if case.sensitive else "passed"


def _outcome(
    case, attempt, started_at, status, latency, ttft, model, answer, kept, error, mask_marker=None
):
    error = clip_error(error, MAX_ERROR_CHARS)  # credentials redacted before the cut
    mismatch = check(case, status, model, kept, answer, error)
    return Outcome(
        case=case.name,
        attempt=attempt,
        started_at=started_at,
        status=status,
        latency_s=round(latency, 4),
        ttft_s=round(ttft, 4) if ttft is not None else None,
        answered_model=model,
        answer=answer[:MAX_ANSWER_CHARS],
        headers=kept,
        error=error,
        expected=not mismatch,
        mismatch=mismatch,
        classification=classify(case, status, answer, error, mask_marker),
    )


async def send_case(
    client: httpx.AsyncClient,
    settings: Settings,
    case: Case,
    headers: dict[str, str],
    attempt: int,
    record_headers: list[str],
    mask_marker: str | None = None,
) -> Outcome:
    proto = protocol(settings, case)
    url = proto.url(case.stream)
    native = isinstance(proto, AnthropicNative)  # names the model once, in message_start
    body = request_body(settings, case, attempt)
    try:
        headers = case_headers(case, headers)
    except ValueError as e:  # recorded like a credential failure, never sent
        return _outcome(case, attempt, time.time(), 0, 0.0, None, None, "", {}, f"credentials: {e}")
    if case.stream:
        headers = {**headers, "Accept-Encoding": "identity"}
    started_at = time.time()
    t0 = time.perf_counter()
    status, error, ttft, model, answer = 0, None, None, None, ""
    got_headers: dict[str, str] = {}
    try:
        if case.stream:
            async with client.stream("POST", url, json=body, headers=headers) as r:
                status, got_headers = r.status_code, dict(r.headers)
                if status >= 400:
                    error = (await r.aread()).decode(errors="replace")
                else:
                    async for data in _sse_events(r.aiter_lines()):
                        if not data or data == "[DONE]":
                            continue
                        event = json.loads(data)
                        if _stream_error(event):
                            error = json.dumps(event)
                            break
                        if native and event.get("type") == "message_start":
                            model = event.get("message", {}).get("model") or model
                        model = event.get("model") or model
                        chunk = proto.text(event)
                        if chunk and ttft is None:
                            ttft = time.perf_counter() - t0
                        answer += chunk
        else:
            r = await client.post(url, json=body, headers=headers)
            status, got_headers = r.status_code, dict(r.headers)
            if status >= 400:
                error = r.text
            else:
                data = r.json()
                model, answer = data.get("model"), proto.text(data)
    except Exception as e:  # noqa: BLE001 - recorded, never fatal to the run
        error = f"{type(e).__name__}: {e}"
    latency = time.perf_counter() - t0
    kept = {k.lower(): redact(v) for k, v in got_headers.items() if k.lower() in record_headers}
    return _outcome(
        case, attempt, started_at, status, latency, ttft, model, answer, kept, error, mask_marker
    )


async def run_file(
    settings: Settings,
    scenario: ScenarioFile,
    headers: Headers,
    sink: Callable[[Outcome], None] | None = None,
) -> list[Outcome]:
    """Every case in order: its attempts one after another, or all at once for a
    `concurrent` case, after its `pause_s`. Each outcome goes to `sink` as soon as it
    exists (a concurrent case's in attempt order once all are back), so an
    interrupted run keeps them."""
    outcomes = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(scenario.timeout_s)) as client:

        async def attempt_once(case: Case, attempt: int) -> Outcome:
            try:
                h = await headers.get()
            except Exception as e:  # noqa: BLE001 - recorded like any failed attempt
                error = f"auth: {type(e).__name__}: {e}"
                return _outcome(case, attempt, time.time(), 0, 0.0, None, None, "", {}, error)
            return await send_case(
                client, settings, case, h, attempt, scenario.record_headers, scenario.mask_marker
            )

        def keep(case: Case, o: Outcome) -> None:
            outcomes.append(o)
            if sink:
                sink(o)
            verdict = "ok" if o.expected else "MISMATCH " + "; ".join(o.mismatch)
            if o.classification:
                verdict += f" [{o.classification}]"
            print(
                f"{case.name} #{o.attempt}: {o.status} {o.latency_s}s "
                f"model={o.answered_model} {verdict}",
                flush=True,
            )

        for case in scenario.cases:
            if case.pause_s:
                print(f"{case.name}: waiting {case.pause_s:g}s", flush=True)
                await _sleep(case.pause_s)
            if case.concurrent:
                batch = [attempt_once(case, a) for a in range(case.repeat)]
                for o in await asyncio.gather(*batch):
                    keep(case, o)
            else:
                for attempt in range(case.repeat):
                    keep(case, await attempt_once(case, attempt))
    return outcomes


def _distinct(values) -> str:
    return ", ".join(sorted({str(v) for v in values if v not in (None, "")})) or "—"


def summary_table(scenario: ScenarioFile, outcomes: list[Outcome]) -> str:
    screening = any(c.ideal for c in scenario.cases)
    cols = ["Case", "Model asked", "Stream", "Expected", "Matched", "Statuses", "Answered by"]
    cols += ["Ideal", "Class"] if screening else []
    cols += [f"`{h}`" for h in scenario.record_headers] + ["p50 s", "Errors"]
    rows = ["| " + " | ".join(cols) + " |", "|" + " --- |" * len(cols)]
    for case in scenario.cases:
        mine = [o for o in outcomes if o.case == case.name]
        if not mine:
            continue
        expect = ", ".join(f"{k}={v}" for k, v in case.expect.items()) or "—"
        cells = [
            case.name,
            case.model,
            "yes" if case.stream else "no",
            expect.replace("|", "/"),
            f"{sum(o.expected for o in mine)}/{len(mine)}",
            _distinct(o.status for o in mine),
            _distinct(o.answered_model for o in mine),
        ]
        if screening:
            cells += [case.ideal or "—", _distinct(o.classification for o in mine)]
        cells += [_distinct(o.headers.get(h) for o in mine) for h in scenario.record_headers]
        cells.append(str(stats.percentile([o.latency_s for o in mine], 50)))
        errors = sorted(
            {o.error.replace("|", "/").replace("\n", " ")[:80] for o in mine if o.error}
        )
        cells.append("; ".join(errors[:2]))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"


def scenarios_markdown(run_id: str, scenario: ScenarioFile, outcomes: list[Outcome]) -> str:
    md = f"# Scenarios {run_id}: {scenario.name}\n\n"
    if scenario.description:
        md += scenario.description + "\n\n"
    md += (
        "A behaviour run, not a measured one: each case sent `repeat` times, one at a "
        "time (all at once for a concurrent case), and latencies are from wherever it "
        "ran. *Matched* counts attempts that met the case's expectations; a mismatch is "
        "a finding, not a harness error. "
        "Full answers and error bodies are in `outcomes.jsonl`.\n\n"
    )
    return md + screening_table(scenario, outcomes) + summary_table(scenario, outcomes)


CLASSES = ("blocked", "masked", "withheld", "leaked", "passed", "error")


def screening_table(scenario: ScenarioFile, outcomes: list[Outcome]) -> str:
    """Attempts per class, by case group, ideal and model (empty without screening cases)."""
    cases = {c.name: c for c in scenario.cases if c.ideal}
    if not cases:
        return ""
    counts: dict[tuple[str, str, str], dict[str, int]] = {}
    for o in outcomes:
        if (c := cases.get(o.case)) is None:
            continue
        key = (c.group or "—", c.ideal or "—", c.model)
        row = counts.setdefault(key, dict.fromkeys(CLASSES, 0))
        row[o.classification or "error"] += 1
    cols = ["Group", "Ideal", "Model", *CLASSES]
    rows = ["| " + " | ".join(cols) + " |", "|" + " --- |" * len(cols)]
    for (group, ideal, model), row in counts.items():
        rows.append(
            f"| {group} | {ideal} | {model} | " + " | ".join(str(row[k]) for k in CLASSES) + " |"
        )
    return "\n".join(rows) + "\n\n"
