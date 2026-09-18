# -*- coding: utf-8 -*-

"""Tests for the PII guardrail: detection, tokenization, and restore."""

import json

import pytest

from kiro.guardrails.apply import apply_findings
from kiro.guardrails.detector import cache_stats, detect, reset_cache
from kiro.guardrails.restore import restore_bytes
from kiro.guardrails.scrubber import SecretFound, anonymize_payload
from kiro.guardrails.vault import PiiVault

ENTITIES = frozenset({"EMAIL", "PHONE_VN", "CCCD", "CARD", "IPV4", "IBAN"})


def _body(*texts: str) -> bytes:
    return json.dumps({
        "model": "claude-opus-5",
        "messages": [{"role": "user", "content": t} for t in texts],
    }).encode()


def _contents(body: bytes) -> list[str]:
    return [m["content"] for m in json.loads(body)["messages"]]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset both caches between tests.

    The guard policy is cached in-process, so without this a test that turns
    the guard on leaks that state into the next one — which is exactly how the
    dashboard switch behaves in production, and exactly what must not leak
    here. The database factory is forced off as well so the resolved policy
    comes from .env alone, regardless of whether the developer running the
    suite happens to have DATABASE_URL set; the tests that do exercise the
    database path patch it back themselves.
    """
    from unittest.mock import patch

    from kiro.guardrails import invalidate_pii_guard_cache

    reset_cache()
    invalidate_pii_guard_cache()
    with patch("kiro.db.engine.async_session_factory", None):
        yield
    reset_cache()
    invalidate_pii_guard_cache()


# --- detection --------------------------------------------------------------

@pytest.mark.parametrize("text,entity", [
    ("lien he an.nguyen+work@example.com nhe", "EMAIL"),
    ("goi 0912345678 giup", "PHONE_VN"),
    ("so +84 90 123 4567", "PHONE_VN"),
    ("cccd 001199012345", "CCCD"),
    ("the 4111 1111 1111 1111", "CARD"),
    ("server 203.0.113.42 down", "IPV4"),
    ("wire to DE89370400440532013000 please", "IBAN"),
])
def test_detects_entity(text, entity):
    results, _ = detect(text, ENTITIES)
    assert entity in {r.entity_type for r in results}, f"{entity} not found in {text!r}"


@pytest.mark.parametrize("text", [
    "listen on 127.0.0.1:8080",          # loopback is infrastructure, not PII
    "internal host 192.168.1.10",        # private range
    "docker bridge 172.17.0.1",          # private range
    "card 4111 1111 1111 1112",          # fails Luhn
    "province code 999888777666",        # 12 digits, invalid province prefix
    "timeout after 123456789 ns",        # bare 9-digit number, CMND off by default
    "version 1.2.3.4000 released",       # octet > 255
    "wire to DE89370400440532013001 please",  # right shape, fails mod-97
])
def test_rejects_false_positive(text):
    results, _ = detect(text, ENTITIES)
    assert results == [], f"false positive on {text!r}: {[r.entity_type for r in results]}"


def test_detection_is_cached_by_content():
    text = "mail an@example.com"
    detect(text, ENTITIES)
    before = cache_stats()["hits"]
    detect(text, ENTITIES)
    assert cache_stats()["hits"] == before + 1


# --- tokenize / restore round trip -----------------------------------------

def test_round_trip_restores_original():
    original = "Mail an@example.com, goi 0912345678."
    body, vault = anonymize_payload(_body(original), ENTITIES)

    scrubbed = _contents(body)[0]
    assert "an@example.com" not in scrubbed
    assert "0912345678" not in scrubbed
    assert "<<EMAIL_1>>" in scrubbed and "<<PHONE_VN_1>>" in scrubbed

    restored = restore_bytes(scrubbed.encode(), vault).decode()
    assert restored == original


def test_same_value_gets_the_same_surrogate():
    """Coreference must survive: presidio's encrypt operator cannot do this."""
    body, vault = anonymize_payload(
        _body("mail an@example.com", "van la an@example.com"), ENTITIES
    )
    first, second = _contents(body)
    assert "<<EMAIL_1>>" in first and "<<EMAIL_1>>" in second
    assert len(vault) == 1


def test_distinct_values_get_distinct_surrogates():
    body, vault = anonymize_payload(_body("a@x.com va b@y.com"), ENTITIES)
    assert "<<EMAIL_1>>" in _contents(body)[0]
    assert "<<EMAIL_2>>" in _contents(body)[0]
    assert len(vault) == 2


def test_non_content_fields_are_untouched():
    payload = json.loads(_body("mail an@example.com"))
    payload["metadata"] = {"trace": "an@example.com"}
    payload["temperature"] = 0.7
    body, _ = anonymize_payload(json.dumps(payload).encode(), ENTITIES)
    out = json.loads(body)
    assert out["metadata"]["trace"] == "an@example.com"
    assert out["temperature"] == 0.7


def test_clean_payload_is_returned_unchanged():
    original = _body("just some ordinary prose with no personal data")
    body, vault = anonymize_payload(original, ENTITIES)
    assert body is original
    assert not vault


def test_non_json_body_passes_through():
    raw = b"not json at all"
    body, vault = anonymize_payload(raw, ENTITIES)
    assert body is raw and not vault


def test_redact_mode_produces_no_vault_entries():
    body, vault = anonymize_payload(_body("mail an@example.com"), ENTITIES, redact_only=True)
    assert "<<EMAIL>>" in _contents(body)[0]
    assert not vault


# --- secrets ----------------------------------------------------------------

@pytest.mark.parametrize("secret", [
    # Gitleaks' anthropic-api-key rule requires exactly 93 body chars plus a
    # literal "AA" suffix — shorter fixtures no longer match the vendored
    # (stricter, more accurate) pattern.
    "sk-ant-api03-" + "a" * 93 + "AA",
    "AKIAJKLMNOPQRSTUVWXY",
    # github-pat also carries a min_entropy=3 floor; a run of one repeated
    # character has zero entropy and is rejected as a placeholder, not a key.
    "ghp_" + "aB3xQ9mK2pL8zN4vC6bH1sD5gU0wY7tRqEfG",
    # private-key's pattern captures header+body+footer as one match, so a
    # fixture needs a real closing marker, not just >=64 filler chars.
    "-----BEGIN RSA PRIVATE KEY-----\n" + "M" * 64 + "\n-----END RSA PRIVATE KEY-----\n",
])
def test_secret_blocks_the_request(secret):
    with pytest.raises(SecretFound):
        anonymize_payload(_body(f"my key is {secret}"), ENTITIES, secret_action="block")


def test_secret_is_forwarded_with_a_warning_by_default():
    """Default policy is warn, not block — a false positive must not 400."""
    body, _ = anonymize_payload(_body("key AKIAJKLMNOPQRSTUVWXY"), ENTITIES)
    assert body is not None  # no raise


def test_secret_scanning_can_be_disabled():
    body, _ = anonymize_payload(
        _body("key AKIAJKLMNOPQRSTUVWXY"), ENTITIES, secret_action="off"
    )
    assert body is not None


def test_secret_error_never_carries_the_value():
    secret = "sk-ant-api03-" + "c" * 93 + "AA"
    with pytest.raises(SecretFound) as exc:
        anonymize_payload(_body(secret), ENTITIES, secret_action="block")
    assert secret not in str(exc.value)


# --- secret false positives (measured against this repo) --------------------

@pytest.mark.parametrize("text,why", [
    ("-----BEGIN RSA PRIVATE KEY-----", "bare PEM header with no key material"),
    ("re.compile(r'-----BEGIN (?:RSA )?PRIVATE KEY-----')", "the header inside library source"),
    ("set OPENAI_API_KEY=sk-proj-abc123def456", "short placeholder key in docs"),
    ("token = 'eyJhbGciOiJ' + '.' + payload + '.' + sig", "JWT-ish string in source"),
    ("AKIAIOSFODNN7EXAMPLE", "AWS's own published documentation example"),
])
def test_credential_lookalikes_are_not_flagged(text, why):
    _, secrets = detect(text, ENTITIES)
    assert secrets == [], f"false positive ({why}): {secrets}"


def test_real_private_key_is_still_flagged():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        + "MIIEowIBAAKCAQEA" + "x" * 60 + "\n"
        + "-----END RSA PRIVATE KEY-----\n"
    )
    _, secrets = detect(pem, ENTITIES)
    assert "PRIVATE_KEY" in secrets


def test_real_jwt_is_still_flagged():
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    # The second segment must itself look like base64 JSON (start with "ey")
    # for gitleaks' jwt pattern to match — a real JWT payload does this
    # naturally because it's also base64 of a JSON object.
    payload = base64.urlsafe_b64encode(
        b'{"sub":"1234567890","name":"John Doe","iat":1516239022}'
    ).decode().rstrip("=")
    jwt = f"{header}.{payload}.{'b' * 30}"
    _, secrets = detect(jwt, ENTITIES)
    assert "JWT" in secrets


@pytest.mark.parametrize("text,entity", [
    # Self-fabricated, format-shaped strings — never a real credential — one
    # per vendor family the gitleaks ruleset adds over the old 11 hand-rolled
    # patterns, to prove the vendored rules actually fire and aren't dead
    # weight sitting behind the keyword gate.
    ("export DO_TOKEN=dop_v1_" + "ab12cd34" * 8, "DIGITALOCEAN_PAT"),
    ("npm config set //registry.npmjs.org/:_authToken=npm_" + ("a1b2c3d4e5" * 4)[:36], "NPM_ACCESS_TOKEN"),
    ("STRIPE_KEY = 'sk_live_" + "aZ9bY8cX7dW6eV5fU4tS3rQ2p'", "STRIPE_ACCESS_TOKEN"),
])
def test_vendored_gitleaks_rules_catch_their_format(text, entity):
    _, secrets = detect(text, ENTITIES)
    assert entity in secrets, f"{entity} not found in {text!r}: {secrets}"


def test_keyword_gate_misses_nothing_a_full_regex_pass_would_find():
    """Differential check: the shared keyword gate is a pre-filter, never a
    stricter substitute for a rule's own pattern. Run every rule's regex
    directly over one realistic sample and compare its hit set against the
    windowed, gated scan — they must agree, or the gate is silently dropping
    real matches instead of just skipping irrelevant rules."""
    from kiro.guardrails.patterns import LITERAL_SECRETS, secret_scan_windows

    sample = (
        "commit message mentioning a token, a secret, and a key\n"
        "export GITHUB_TOKEN=ghp_aB3xQ9mK2pL8zN4vC6bH1sD5gU0wY7tRqEfG\n"
        "DO_TOKEN=dop_v1_" + "ab12cd34" * 8 + "\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA" + "x" * 60
        + "\n-----END RSA PRIVATE KEY-----\n"
    )
    lowered = sample.lower()

    gated_hits: set[tuple[int, int, int]] = set()
    for idx, spans in secret_scan_windows(lowered).items():
        rule = LITERAL_SECRETS[idx]
        for lo, hi in spans:
            for m in rule.pattern.finditer(sample, lo, hi):
                gated_hits.add((idx, m.start(), m.end()))

    full_hits: set[tuple[int, int, int]] = set()
    for idx, rule in enumerate(LITERAL_SECRETS):
        for m in rule.pattern.finditer(sample):
            full_hits.add((idx, m.start(), m.end()))

    assert gated_hits == full_hits, (
        "gate/window scan disagrees with a full pass over the same text — "
        f"missing={full_hits - gated_hits} extra={gated_hits - full_hits}"
    )


# --- streaming restore ------------------------------------------------------
#
# A surrogate is several model tokens, and an SSE frame carries about one, so
# in practice a surrogate is ALWAYS split across frames with protocol framing
# in between. These tests pin that down: no single chunk ever contains the
# whole surrogate.

def _sse(*texts: str) -> list[bytes]:
    """One OpenAI-shaped SSE frame per text fragment."""
    return [
        b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n\n"
        for t in texts
    ]


def _run_stream(vault, chunks, sse=True, restore_tool_args=None) -> bytes:
    import asyncio

    from kiro.guardrails.restore import restore_stream

    async def _source():
        for c in chunks:
            yield c

    async def _collect():
        return b"".join([
            c async for c in restore_stream(_source(), vault, sse, restore_tool_args)
        ])

    return asyncio.run(_collect())


def _deltas(stream: bytes) -> str:
    """Concatenate the model-visible text out of an SSE byte stream."""
    text = ""
    for frame in stream.split(b"\n\n"):
        for line in frame.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw in (b"[DONE]", b""):
                continue
            payload = json.loads(raw)
            for choice in payload.get("choices", []):
                text += choice.get("delta", {}).get("content") or ""
    return text


def test_surrogate_split_across_frames_is_restored():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")

    # Split the surrogate the way a tokenizer would: "<<", "EMAIL", "_1", ">>".
    frames = _sse("mail ", "<<", "EMAIL", "_1", ">>", " da nhan")
    for f in frames:
        assert token.encode() not in f, "test is invalid: a frame held the whole token"

    out = _run_stream(vault, frames + [b"data: [DONE]\n\n"])
    assert _deltas(out) == "mail an@example.com da nhan"


def test_surrogate_restored_at_every_split_point():
    vault = PiiVault()
    token = vault.token_for("PHONE_VN", "0912345678")
    full = f"goi {token} nhe"
    for cut in range(1, len(full)):
        out = _run_stream(vault, _sse(full[:cut], full[cut:]) + [b"data: [DONE]\n\n"])
        assert _deltas(out) == "goi 0912345678 nhe", f"failed at split {cut}"


def test_restored_when_fed_one_byte_at_a_time():
    """Frame reassembly must also survive arbitrary transport chunking."""
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    raw = b"".join(_sse("mail ", token[:4], token[4:], " ok") + [b"data: [DONE]\n\n"])
    out = _run_stream(vault, [raw[i:i + 1] for i in range(len(raw))])
    assert _deltas(out) == "mail an@example.com ok"


def test_surrogate_at_end_of_stream_is_flushed_before_done():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    out = _run_stream(vault, _sse("lien he ", token) + [b"data: [DONE]\n\n"])
    assert _deltas(out) == "lien he an@example.com"
    assert out.rstrip().endswith(b"data: [DONE]"), "DONE must stay last"


def test_surrogate_at_end_without_done_is_still_flushed():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    out = _run_stream(vault, _sse("lien he ", token))
    assert _deltas(out) == "lien he an@example.com"


def test_unknown_surrogate_passes_through_instead_of_raising():
    vault = PiiVault()
    vault.token_for("EMAIL", "an@example.com")
    out = _run_stream(vault, _sse("see <<EMAIL_99>> here"))
    assert _deltas(out) == "see <<EMAIL_99>> here"


def test_value_needing_json_escaping_survives():
    vault = PiiVault()
    token = vault.token_for("EMAIL", 'we"ird\\name@example.com')
    out = _run_stream(vault, _sse(token))
    assert _deltas(out) == 'we"ird\\name@example.com'


def test_angle_brackets_in_output_are_not_swallowed():
    vault = PiiVault()
    vault.token_for("EMAIL", "an@example.com")
    out = _run_stream(vault, _sse("<div>", "<span>x</span>", "</div>"))
    assert _deltas(out) == "<div><span>x</span></div>"


def test_stream_without_surrogates_preserves_text():
    vault = PiiVault()
    vault.token_for("EMAIL", "an@example.com")
    out = _run_stream(vault, _sse("hello ", "world") + [b"data: [DONE]\n\n"])
    assert _deltas(out) == "hello world"


def test_anthropic_shaped_frames_are_restored():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    frames = [
        b"event: content_block_delta\ndata: "
        + json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": t}}).encode()
        + b"\n\n"
        for t in ("mail ", token[:5], token[5:])
    ]
    out = _run_stream(vault, frames)
    text = ""
    for frame in out.split(b"\n\n"):
        for line in frame.split(b"\n"):
            if line.startswith(b"data:"):
                text += json.loads(line[5:].strip()).get("delta", {}).get("text", "")
    assert text == "mail an@example.com"


def test_non_sse_body_is_buffered_and_restored():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    body = json.dumps({"choices": [{"message": {"content": f"mail {token}"}}]}).encode()
    out = _run_stream(vault, [body[:20], body[20:]], sse=False)
    assert json.loads(out)["choices"][0]["message"]["content"] == "mail an@example.com"


def test_restore_bytes_escapes_for_json_context():
    vault = PiiVault()
    token = vault.token_for("EMAIL", 'we"ird@example.com')
    out = restore_bytes(f'{{"content":"{token}"}}'.encode(), vault)
    assert json.loads(out)["content"] == 'we"ird@example.com'


def test_crossing_spans_do_not_leak_the_uncovered_tail():
    """Two spans that cross must both be fully covered, not partly dropped."""
    from kiro.guardrails.findings import Finding

    text = "abcdefghijklmnop"
    # IPV4 spans 2..8, EMAIL spans 5..12 — neither contains the other.
    out, n = apply_findings(
        text,
        [Finding("IPV4", 2, 8), Finding("EMAIL", 5, 12)],
        lambda et, matched: "<X>",
    )
    assert out == "ab<X>mnop"
    assert n == 1
    # Nothing between offsets 2 and 12 survives in the clear.
    assert "fgh" not in out and "ijkl" not in out


# --- tool calls -------------------------------------------------------------
#
# The request side tokenizes tool arguments, so the response side has to put
# them back: a tool that runs against "<<EMAIL_1>>" instead of the address is
# a silent, user-visible failure, and unlike prose nobody can eyeball it.
# Arguments stream as fragments of JSON *source*, so the restored value also
# has to be escaped for the string literal it lands in.

def _tool_frames(fragments, index=0):
    """OpenAI-shaped tool-call frames, one arguments fragment each."""
    return [
        b"data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": index, "function": {"arguments": f}}]}}]}).encode() + b"\n\n"
        for f in fragments
    ]


def _tool_arguments(stream: bytes) -> dict[int, str]:
    """Reassemble each tool call's arguments the way a client does."""
    acc: dict[int, str] = {}
    for frame in stream.split(b"\n\n"):
        for line in frame.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw in (b"[DONE]", b""):
                continue
            for choice in json.loads(raw).get("choices", []):
                for call in choice.get("delta", {}).get("tool_calls", []):
                    acc[call["index"]] = acc.get(call["index"], "") + (
                        call.get("function", {}).get("arguments") or ""
                    )
    return acc


def test_tool_arguments_are_restored_before_the_client_executes():
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    whole = '{"to":"' + token + '"}'
    frames = _tool_frames([whole[i:i + 4] for i in range(0, len(whole), 4)])
    out = _run_stream(vault, frames)
    assert json.loads(_tool_arguments(out)[0]) == {"to": "an@example.com"}


def test_restored_tool_argument_keeps_the_arguments_parseable():
    # The original carries characters that are special inside a JSON string.
    vault = PiiVault()
    token = vault.token_for("EMAIL", 'we"ird\\name@example.com')
    whole = '{"to":"' + token + '"}'
    frames = _tool_frames([whole[i:i + 3] for i in range(0, len(whole), 3)])
    out = _run_stream(vault, frames)
    assert json.loads(_tool_arguments(out)[0]) == {"to": 'we"ird\\name@example.com'}


def test_parallel_tool_calls_do_not_swap_held_back_text():
    vault = PiiVault()
    first = '{"to":"' + vault.token_for("EMAIL", "zero@example.com") + '"}'
    second = '{"to":"' + vault.token_for("EMAIL", "one@example.com") + '"}'
    frames = [
        b"data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": first[i:i + 3]}},
            {"index": 1, "function": {"arguments": second[i:i + 3]}},
        ]}}]}).encode() + b"\n\n"
        for i in range(0, max(len(first), len(second)), 3)
    ]
    args = _tool_arguments(_run_stream(vault, frames))
    assert json.loads(args[0]) == {"to": "zero@example.com"}
    assert json.loads(args[1]) == {"to": "one@example.com"}


def test_anthropic_tool_input_deltas_are_restored():
    vault = PiiVault()
    whole = '{"phone":"' + vault.token_for("PHONE_VN", "0901234567") + '"}'
    frames = [
        b"event: content_block_delta\ndata: " + json.dumps({
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": whole[i:i + 5]},
        }).encode() + b"\n\n"
        for i in range(0, len(whole), 5)
    ]
    out = _run_stream(vault, frames)
    acc = ""
    for frame in out.split(b"\n\n"):
        for line in frame.split(b"\n"):
            if line.startswith(b"data:") and line[5:].strip():
                acc += json.loads(line[5:].strip())["delta"]["partial_json"]
    assert json.loads(acc) == {"phone": "0901234567"}


def test_prose_and_tool_arguments_in_one_stream_both_restore():
    """The realistic shape: the model explains, then calls a tool."""
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    whole = '{"to":"' + token + '"}'
    frames = (
        _sse("Sending to ", token[:6], token[6:], ". ")
        + _tool_frames([whole[i:i + 4] for i in range(0, len(whole), 4)])
    )
    out = _run_stream(vault, frames)
    assert _deltas(out) == "Sending to an@example.com. "
    assert json.loads(_tool_arguments(out)[0]) == {"to": "an@example.com"}


# --- end to end through forward_to_nine_router ------------------------------

class TestForwardIntegration:
    """The guard is wired into the one function that owns both directions."""

    @staticmethod
    def _request():
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import Request
        from starlette.datastructures import Headers

        req = MagicMock(spec=Request)
        req.method = "POST"
        req.url.path = "/v1/chat/completions"
        req.url.query = ""
        req.headers = Headers({"content-type": "application/json"})
        req.body = AsyncMock(return_value=b"{}")
        req.app.state.http_client = None
        return req

    @staticmethod
    def _upstream(chunks):
        from unittest.mock import AsyncMock, MagicMock

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}

        async def _aiter():
            for c in chunks:
                yield c

        resp.aiter_bytes = _aiter
        resp.aread = AsyncMock(return_value=b"error body")
        resp.aclose = AsyncMock()
        return resp

    @staticmethod
    def _client(response, sent):
        from unittest.mock import AsyncMock, MagicMock

        client = MagicMock()

        def build(**kwargs):
            sent.append(kwargs)
            return kwargs

        client.build_request = MagicMock(side_effect=build)
        client.send = AsyncMock(return_value=response)
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_pii_tokenized_upstream_and_restored_downstream(self):
        from unittest.mock import patch

        import kiro.config as cfg
        import kiro.nine_router_client as mod

        # The model echoes the surrogate back, split across two SSE frames.
        upstream_chunks = [
            b'data: {"choices":[{"delta":{"content":"mail <<EMA"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"IL_1>> da nhan"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
        sent = []
        client = self._client(self._upstream(upstream_chunks), sent)
        body = _body("gui toi an@example.com giup")

        with (
            patch.object(cfg, "PII_GUARD_MODE", "tokenize"),
            patch.object(cfg, "PII_ENTITIES", ENTITIES),
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            resp = await mod.forward_to_nine_router(self._request(), body)
            out = b"".join([c async for c in resp.body_iterator])

        upstream_body = sent[0]["content"]
        assert b"an@example.com" not in upstream_body, "PII reached 9router"
        assert b"<<EMAIL_1>>" in upstream_body

        assert b"an@example.com" in out, "PII not restored for the client"
        assert b"<<EMAIL_1>>" not in out

    @pytest.mark.asyncio
    async def test_secret_is_rejected_without_contacting_upstream(self):
        from unittest.mock import patch

        from fastapi.responses import JSONResponse

        import kiro.config as cfg
        import kiro.nine_router_client as mod

        sent = []
        client = self._client(self._upstream([b""]), sent)
        body = _body("key sk-ant-api03-" + "a" * 93 + "AA")

        with (
            patch.object(cfg, "PII_GUARD_MODE", "tokenize"),
            patch.object(cfg, "PII_ENTITIES", ENTITIES),
            patch.object(cfg, "PII_SECRET_ACTION", "block"),
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            resp = await mod.forward_to_nine_router(self._request(), body)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 400
        assert sent == [], "blocked request still went upstream"

    @pytest.mark.asyncio
    async def test_guard_off_leaves_the_payload_untouched(self):
        from unittest.mock import patch

        import kiro.config as cfg
        import kiro.nine_router_client as mod

        chunks = [b'data: {"delta":"hi"}\n\n', b"data: [DONE]\n\n"]
        sent = []
        client = self._client(self._upstream(chunks), sent)
        body = _body("gui toi an@example.com giup")

        with (
            patch.object(cfg, "PII_GUARD_MODE", "off"),
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            resp = await mod.forward_to_nine_router(self._request(), body)
            out = b"".join([c async for c in resp.body_iterator])

        # Byte-identical, not just JSON-equal: with no override configured the
        # override candidate is just the unchanged model, so the rewrite is
        # skipped entirely and the original bytes go upstream untouched.
        assert sent[0]["content"] == body
        assert out == b"".join(chunks)

    @pytest.mark.asyncio
    async def test_no_override_forwards_body_byte_identical(self):
        """Regression test for the wasted re-serialize on the hot path.

        With the model override disabled, `candidates = [original_model]`
        exactly reproduces the model already in the body — there is nothing
        to rewrite. Use an indented (non-compact) body: if
        `_rewrite_model_in_body` ran, it would re-serialize with
        `separators=(",", ":")` and silently strip the formatting. Asserting
        identity (not just JSON-equality) pins down that the rewrite never
        ran at all.
        """
        from unittest.mock import patch

        import kiro.config as cfg
        import kiro.nine_router_client as mod

        chunks = [b'data: {"delta":"hi"}\n\n', b"data: [DONE]\n\n"]
        sent = []
        client = self._client(self._upstream(chunks), sent)
        body = json.dumps(
            {"model": "claude-opus-5", "messages": [{"role": "user", "content": "hi"}]},
            indent=2,
        ).encode()

        with (
            patch.object(cfg, "PII_GUARD_MODE", "off"),
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("kiro.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            await mod.forward_to_nine_router(self._request(), body)

        assert sent[0]["content"] is body, "body was re-serialized when it should have been forwarded as-is"


def test_substitution_stays_linear_in_span_count():
    """Regression guard on the reason presidio was dropped.

    Its AnonymizerEngine was quadratic: 25 -> 800 spans took 0.73ms -> 225ms
    on a fixed text. The bound here is deliberately loose (it only has to fail
    on a reintroduced quadratic, not on a slow CI box).
    """
    import time

    text = "contact person@example.com about it. " * 800
    findings, _ = detect(text, ENTITIES)
    assert len(findings) >= 500, "corpus should be span-dense for this to mean anything"

    vault = PiiVault()
    start = time.perf_counter()
    apply_findings(text, findings, lambda et, m: vault.token_for(et, m))
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 50, f"{len(findings)} spans took {elapsed_ms:.1f}ms — quadratic again?"


# --- switches: master off, tool-args restore, fail-open ----------------------

def _policy(mode="off", secret_action="warn", restore_tool_args=True):
    """Pin the resolved policy, bypassing both .env and the database."""
    from unittest.mock import patch

    from kiro.guardrails import PiiPolicy

    async def _fake():
        return PiiPolicy(mode, secret_action, restore_tool_args)

    return patch("kiro.guardrails.get_pii_policy", _fake)


def test_guard_off_returns_body_unmodified_and_creates_no_vault():
    """Mode "off" is the master switch. This pins down more than the
    forward-integration test does: scrub_request itself must return the
    exact same bytes object's content untouched and `None` for the vault,
    not just an empty one — nothing about the request is even parsed."""
    import asyncio

    from kiro.guardrails import scrub_request

    body = _body("mail an@example.com, the 4111 1111 1111 1111")
    with _policy(mode="off"):
        out, vault, _ = asyncio.run(scrub_request(body))

    assert out == body
    assert vault is None


# --- runtime policy: the dashboard switch -----------------------------------
#
# The switch exists to stop a misbehaving guard while traffic is flowing, so
# what matters is that the database wins over .env, that a database problem
# never turns the guard ON by itself, and that a write takes effect without a
# restart.

def _policy_from_db(values: dict[str, str | None]):
    """Run get_pii_policy against a fake system_config table."""
    import asyncio
    from unittest.mock import patch

    import kiro.guardrails as g

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def _get_config(_session, key):
        return values[key]

    g.invalidate_pii_guard_cache()
    try:
        with patch("kiro.db.engine.async_session_factory", _Session), \
             patch("kiro.db.repositories.get_config", _get_config):
            return asyncio.run(g.get_pii_policy())
    finally:
        g.invalidate_pii_guard_cache()


def test_dashboard_setting_overrides_the_env_default():
    policy = _policy_from_db({
        "pii_guard_mode": "tokenize",
        "pii_secret_action": "block",
        "pii_restore_tool_args": "false",
    })
    assert policy.mode == "tokenize"
    assert policy.secret_action == "block"
    assert policy.restore_tool_args is False


def test_unset_dashboard_keys_fall_back_to_env():
    from kiro.config import PII_GUARD_MODE, PII_SECRET_ACTION

    policy = _policy_from_db({
        "pii_guard_mode": None,
        "pii_secret_action": None,
        "pii_restore_tool_args": None,
    })
    assert policy.mode == PII_GUARD_MODE
    assert policy.secret_action == PII_SECRET_ACTION


def test_garbage_in_the_database_does_not_enable_the_guard():
    """A value this build does not recognise must be ignored, not guessed at."""
    from kiro.config import PII_GUARD_MODE

    policy = _policy_from_db({
        "pii_guard_mode": "tokenise",          # British spelling: not a mode
        "pii_secret_action": "explode",
        "pii_restore_tool_args": None,
    })
    assert policy.mode == PII_GUARD_MODE
    assert policy.secret_action in ("off", "warn", "block")


def test_database_failure_leaves_the_env_policy_in_force():
    """A database outage must not switch the guard on — or off — by surprise."""
    import asyncio
    from unittest.mock import patch

    import kiro.guardrails as g
    from kiro.config import PII_GUARD_MODE

    def _boom():
        raise RuntimeError("database is down")

    g.invalidate_pii_guard_cache()
    try:
        with patch("kiro.db.engine.async_session_factory", _boom):
            policy = asyncio.run(g.get_pii_policy())
    finally:
        g.invalidate_pii_guard_cache()

    assert policy.mode == PII_GUARD_MODE


def test_config_route_shows_the_env_policy_when_nothing_is_stored():
    """The dashboard must render the state the gateway is actually in.

    Both sides apply the same .env-as-floor rule, so an admin who has never
    touched the switch still sees the real mode rather than a hardcoded "off".
    """
    from kiro.config import PII_GUARD_MODE, PII_RESTORE_TOOL_ARGS
    from kiro.dashboard.routes_config import _to_response

    out = _to_response({})
    assert out.pii_guard_mode == PII_GUARD_MODE
    assert out.pii_restore_tool_args is PII_RESTORE_TOOL_ARGS


def test_config_route_stored_value_wins_over_env():
    from kiro.dashboard.routes_config import _to_response

    out = _to_response({"pii_guard_mode": "redact", "pii_restore_tool_args": "false"})
    assert out.pii_guard_mode == "redact"
    assert out.pii_restore_tool_args is False


def test_api_rejects_a_mode_the_gateway_cannot_honour():
    """Caught at the schema, so a typo cannot be written to system_config and
    then silently ignored by the resolver."""
    import pytest as _pytest
    from pydantic import ValidationError

    from kiro.dashboard.schemas import SystemConfigUpdate

    with _pytest.raises(ValidationError):
        SystemConfigUpdate(pii_guard_mode="tokenise")


def test_policy_is_cached_until_invalidated():
    """Resolved once per request burst, and a dashboard write drops it."""
    import asyncio
    from unittest.mock import patch

    import kiro.guardrails as g

    calls = {"n": 0}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def _get_config(_session, key):
        calls["n"] += 1
        return None

    g.invalidate_pii_guard_cache()
    try:
        with patch("kiro.db.engine.async_session_factory", _Session), \
             patch("kiro.db.repositories.get_config", _get_config):
            asyncio.run(g.get_pii_policy())
            after_first = calls["n"]
            asyncio.run(g.get_pii_policy())
            assert calls["n"] == after_first, "second call should hit the cache"

            g.invalidate_pii_guard_cache()
            asyncio.run(g.get_pii_policy())
            assert calls["n"] > after_first, "invalidate must force a re-read"
    finally:
        g.invalidate_pii_guard_cache()


def test_restore_tool_args_false_leaves_tool_argument_surrogate_untouched():
    """PII_RESTORE_TOOL_ARGS=false must disable restoring only the
    arguments/partial_json surface — the finer-grained switch for the
    riskiest restore path, without giving up tokenize mode entirely."""
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    whole = '{"to":"' + token + '"}'
    frames = _tool_frames([whole[i:i + 4] for i in range(0, len(whole), 4)])

    out = _run_stream(vault, frames, restore_tool_args=False)

    args = _tool_arguments(out)[0]
    assert token in args, "surrogate should still be literal in the arguments"
    assert "an@example.com" not in args


def test_restore_tool_args_false_still_restores_prose():
    """The switch is scoped to tool arguments only — prose in the same
    stream must keep restoring normally."""
    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    whole = '{"to":"' + token + '"}'
    frames = (
        _sse("Sending to ", token[:6], token[6:], ". ")
        + _tool_frames([whole[i:i + 4] for i in range(0, len(whole), 4)])
    )

    out = _run_stream(vault, frames, restore_tool_args=False)

    assert _deltas(out) == "Sending to an@example.com. "
    assert token in _tool_arguments(out)[0]


def test_restore_tool_args_defaults_to_config():
    """With no explicit argument, restore_stream must read
    PII_RESTORE_TOOL_ARGS itself (production callers pass nothing)."""
    from unittest.mock import patch

    import kiro.config as cfg

    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    whole = '{"to":"' + token + '"}'
    frames = _tool_frames([whole[i:i + 4] for i in range(0, len(whole), 4)])

    with patch.object(cfg, "PII_RESTORE_TOOL_ARGS", False):
        out = _run_stream(vault, frames)  # restore_tool_args=None -> reads config

    assert token in _tool_arguments(out)[0]


def test_restore_stream_fails_open_on_unexpected_error():
    """An exception inside SseRestorer.feed() must not propagate and kill the
    response mid-stream: it is logged once, and the rest of the stream from
    the failing chunk onward is passed through raw instead. A surrogate
    reaching the client is bad; a broken stream is worse."""
    import asyncio
    from unittest.mock import patch

    from kiro.guardrails.restore import SseRestorer, restore_stream

    vault = PiiVault()
    token = vault.token_for("EMAIL", "an@example.com")
    ok_frame = _sse("all good")[0]
    boom_frame = _sse(f"leaks {token} here")[0]
    tail_frame = _sse("still arrives")[0]
    frames = [ok_frame, boom_frame, tail_frame]

    real_feed = SseRestorer.feed
    calls = {"n": 0}

    def _flaky(self, chunk):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real_feed(self, chunk)

    async def _source():
        for f in frames:
            yield f

    async def _collect():
        with patch.object(SseRestorer, "feed", _flaky):
            return b"".join([c async for c in restore_stream(_source(), vault)])

    out = asyncio.run(_collect())  # must not raise despite the injected error

    # The failing frame and everything after arrive byte-for-byte raw —
    # unmodified rather than dropped — and since it was never restored, the
    # surrogate stays literal instead of leaking the real email either.
    assert boom_frame in out
    assert tail_frame in out
    assert b"an@example.com" not in out
