# -*- coding: utf-8 -*-
"""
Unit tests for kiro/nine_router_client.py.

Tests cover:
- is_nine_router_enabled()
- forward_to_nine_router() — fallback triggered, not triggered, streaming passthrough
- Error handling: connect error, timeout, non-200 upstream, disabled
"""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.datastructures import Headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_model_cooldown():
    """Cooldown state is module-global — keep tests independent."""
    import aigw.nine_router_client as mod
    mod._model_cooldown.clear()
    yield
    mod._model_cooldown.clear()


def _mock_request(
    method: str = "POST",
    path: str = "/v1/chat/completions",
    query: str = "",
    headers: dict | None = None,
    shared_http_client=None,
) -> MagicMock:
    req = MagicMock(spec=Request)
    req.method = method
    req.url.path = path
    req.url.query = query
    req.headers = Headers(headers or {"content-type": "application/json"})
    req.body = AsyncMock(return_value=b'{"model":"gpt-4","messages":[]}')
    # Simulate app.state.http_client — None triggers private-client fallback
    req.app.state.http_client = shared_http_client
    return req


def _mock_stream_response(status_code: int = 200, chunks: list[bytes] | None = None, headers: dict | None = None):
    chunks = chunks or [b"data: chunk1\n\n", b"data: [DONE]\n\n"]
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {"content-type": "text/event-stream"}

    async def _aiter():
        for c in chunks:
            yield c

    resp.aiter_bytes = _aiter
    resp.aread = AsyncMock(return_value=b"error body")
    resp.aclose = AsyncMock()
    return resp


def _mock_client(response=None, send_side_effect=None):
    client = MagicMock()
    client.timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=10.0)
    client.build_request = MagicMock(side_effect=lambda **kwargs: kwargs)
    client.send = AsyncMock(side_effect=send_side_effect) if send_side_effect else AsyncMock(return_value=response)
    client.aclose = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# is_nine_router_enabled
# ---------------------------------------------------------------------------

class TestIsNineRouterEnabled:
    def test_enabled_when_url_set(self):
        import aigw.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"):
            assert mod.is_nine_router_enabled() is True

    def test_disabled_when_url_empty(self):
        import aigw.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", ""):
            assert mod.is_nine_router_enabled() is False


# ---------------------------------------------------------------------------
# forward_to_nine_router
# ---------------------------------------------------------------------------

class TestForwardToNineRouter:
    @pytest.mark.asyncio
    async def test_returns_503_when_not_configured(self):
        import aigw.nine_router_client as mod
        with patch.object(mod, "NINE_ROUTER_URL", ""):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_streams_response_on_success(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, StreamingResponse)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [b'{"model":"m","stream":false}', b'{"model":"m"}'])
    async def test_non_stream_uses_long_read_timeout(self, body):
        """Non-stream: 9router replies only after full generation — read timeout is extended."""
        import aigw.nine_router_client as mod
        client = _mock_client(response=_mock_stream_response(200))

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_NONSTREAM_READ_TIMEOUT", 570.0),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            await mod.forward_to_nine_router(_mock_request(), body)
            timeout = client.build_request.call_args.kwargs["timeout"]
            assert timeout.read == 570.0
            assert timeout.connect == 30.0 and timeout.pool == 10.0

    @pytest.mark.asyncio
    async def test_stream_read_timeout_outlasts_9router_stall_watchdog(self):
        """Stream: read timeout is raised past 9router's stall watchdog (360s)."""
        import aigw.nine_router_client as mod
        client = _mock_client(response=_mock_stream_response(200))

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_STREAM_READ_TIMEOUT", 420.0),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            await mod.forward_to_nine_router(_mock_request(), b'{"model":"m","stream":true}')
            timeout = client.build_request.call_args.kwargs["timeout"]
            assert timeout.read == 420.0
            assert timeout.connect == 30.0 and timeout.pool == 10.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path,marker",
        [("/v1/messages", b"event: error"), ("/v1/chat/completions", b'"type": "upstream_error"')],
    )
    async def test_mid_stream_failure_emits_sse_error_event(self, path, marker):
        import aigw.nine_router_client as mod
        resp_up = _mock_stream_response(200)

        async def _broken():
            yield b"data: partial\n\n"
            raise httpx.ReadTimeout("stalled")

        resp_up.aiter_bytes = _broken
        client = _mock_client(response=resp_up)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            resp = await mod.forward_to_nine_router(_mock_request(path=path), b'{"model":"m","stream":true}')
            chunks = [c async for c in resp.body_iterator]

        assert chunks[0] == b"data: partial\n\n"
        assert marker in chunks[-1]
        resp_up.aclose.assert_awaited()

    @pytest.mark.asyncio
    async def test_adds_api_key_header_when_configured(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", "secret-key"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            await mod.forward_to_nine_router(req, b"{}")
            sent_headers = client.build_request.call_args.kwargs["headers"]
            assert sent_headers.get("Authorization") == "Bearer secret-key"

    @pytest.mark.asyncio
    async def test_strips_original_authorization_header(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", ""),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request(headers={"authorization": "Bearer gateway-user-token"})
            await mod.forward_to_nine_router(req, b"{}")
            sent_headers = client.build_request.call_args.kwargs["headers"]
            assert "Authorization" not in sent_headers
            assert "authorization" not in sent_headers

    @pytest.mark.asyncio
    async def test_non_200_upstream_returns_json_error(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(429)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_connect_error_returns_503(self):
        import aigw.nine_router_client as mod
        import httpx

        client = _mock_client(send_side_effect=httpx.ConnectError("refused"))

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_timeout_returns_504(self):
        import aigw.nine_router_client as mod
        import httpx

        client = _mock_client(send_side_effect=httpx.TimeoutException("timed out"))

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 504

    @pytest.mark.asyncio
    async def test_correct_target_url_built(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request(path="/v1/chat/completions")
            await mod.forward_to_nine_router(req, b"{}")
            built_url = client.build_request.call_args.kwargs["url"]
            assert built_url == "http://ninerouter:20128/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_query_string_forwarded(self):
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        client = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request(path="/v1/models", query="foo=bar")
            await mod.forward_to_nine_router(req, b"")
            built_url = client.build_request.call_args.kwargs["url"]
            assert "foo=bar" in built_url

    @pytest.mark.asyncio
    async def test_shared_client_reused_and_not_closed(self):
        """When app.state.http_client exists, it's used directly and never closed."""
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        shared = _mock_client(response=resp_mock)

        with patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"):
            req = _mock_request(shared_http_client=shared)
            resp = await mod.forward_to_nine_router(req, b"{}")
            assert isinstance(resp, StreamingResponse)
            # Drain stream to trigger finally block
            async for _ in resp.body_iterator:
                pass
            # Connection returned to pool (response closed), but client NOT closed
            resp_mock.aclose.assert_awaited()
            shared.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_private_client_closed_after_stream(self):
        """When no shared client, a private client is created and closed after stream."""
        import aigw.nine_router_client as mod
        resp_mock = _mock_stream_response(200)
        private = _mock_client(response=resp_mock)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=private),
        ):
            req = _mock_request()  # shared_http_client=None (default)
            resp = await mod.forward_to_nine_router(req, b"{}")
            async for _ in resp.body_iterator:
                pass
            # Both response and private client are closed
            resp_mock.aclose.assert_awaited()
            private.aclose.assert_awaited()


# ---------------------------------------------------------------------------
# on_usage callback (usage recording for the fallback path)
# ---------------------------------------------------------------------------

async def _drain(streaming_response) -> list[bytes]:
    """Iterate a StreamingResponse body to completion, returning the chunks."""
    chunks = []
    async for chunk in streaming_response.body_iterator:
        chunks.append(chunk)
    return chunks


class TestOnUsageCallback:
    @pytest.mark.asyncio
    async def test_callback_fired_with_openai_usage(self):
        import aigw.nine_router_client as mod
        chunks = [
            b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n',
            b'data: {"model":"gpt-4o","usage":{"prompt_tokens":12,"completion_tokens":7}}\n\n',
            b"data: [DONE]\n\n",
        ]
        resp_mock = _mock_stream_response(200, chunks=chunks)
        client = _mock_client(response=resp_mock)
        seen = {}

        async def on_usage(it, ot, model):
            seen["input"], seen["output"], seen["model"] = it, ot, model

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}", on_usage=on_usage)
            body = await _drain(resp)

        assert body == chunks  # stream passed through unchanged
        assert seen == {"input": 12, "output": 7, "model": "gpt-4o"}

    @pytest.mark.asyncio
    async def test_callback_fired_with_anthropic_usage(self):
        import aigw.nine_router_client as mod
        chunks = [
            b'event: message_start\ndata: {"type":"message_start","message":{"model":"claude-opus-4-8","usage":{"input_tokens":30}}}\n\n',
            b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":15}}\n\n',
        ]
        resp_mock = _mock_stream_response(200, chunks=chunks)
        client = _mock_client(response=resp_mock)
        seen = {}

        async def on_usage(it, ot, model):
            seen["input"], seen["output"], seen["model"] = it, ot, model

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request(path="/v1/messages")
            resp = await mod.forward_to_nine_router(req, b"{}", on_usage=on_usage)
            await _drain(resp)

        assert seen == {"input": 30, "output": 15, "model": "claude-opus-4-8"}

    @pytest.mark.parametrize(
        "chunk, expected_input",
        [
            # Anthropic: cache reads/writes are reported beside input_tokens and
            # must be added back, or a cached agent loop bills ~16 input tokens.
            (
                'data: {"type":"message_start","message":{"usage":{"input_tokens":16,'
                '"cache_creation_input_tokens":500,"cache_read_input_tokens":90000}}}\n\n',
                90516,
            ),
            # 9router's OpenAI translation carries both prompt_tokens (cache
            # included) and input_tokens (uncached only) — prompt_tokens wins.
            (
                'data: {"usage":{"prompt_tokens":90516,"input_tokens":16,'
                '"completion_tokens":5}}\n\n',
                90516,
            ),
        ],
    )
    def test_input_includes_cached_tokens(self, chunk, expected_input):
        import aigw.nine_router_client as mod
        counts = {"input": 0, "output": 0}
        mod._accumulate_usage_from_chunk(chunk, counts, [None])
        assert counts["input"] == expected_input

    def test_output_only_delta_keeps_cached_input(self):
        import aigw.nine_router_client as mod
        counts = {"input": 0, "output": 0}
        mod._accumulate_usage_from_chunk(
            'data: {"type":"message_start","message":{"usage":{"input_tokens":16,'
            '"cache_read_input_tokens":1000}}}\n\n',
            counts,
            [None],
        )
        mod._accumulate_usage_from_chunk(
            'data: {"type":"message_delta","usage":{"output_tokens":42}}\n\n', counts, [None]
        )
        assert counts == {"input": 1016, "output": 42}

    @pytest.mark.asyncio
    async def test_callback_fired_with_zeroes_when_no_usage(self):
        import aigw.nine_router_client as mod
        chunks = [b"data: chunk1\n\n", b"data: [DONE]\n\n"]
        resp_mock = _mock_stream_response(200, chunks=chunks)
        client = _mock_client(response=resp_mock)
        seen = {}

        async def on_usage(it, ot, model):
            seen["input"], seen["output"], seen["model"] = it, ot, model

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}", on_usage=on_usage)
            await _drain(resp)

        assert seen == {"input": 0, "output": 0, "model": "unknown"}

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_break_stream(self):
        import aigw.nine_router_client as mod
        chunks = [
            b'data: {"model":"gpt-4o","usage":{"prompt_tokens":1,"completion_tokens":1}}\n\n',
            b"data: [DONE]\n\n",
        ]
        resp_mock = _mock_stream_response(200, chunks=chunks)
        client = _mock_client(response=resp_mock)

        async def on_usage(it, ot, model):
            raise RuntimeError("tracking blew up")

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, b"{}", on_usage=on_usage)
            body = await _drain(resp)  # must not raise

        assert body == chunks
        resp_mock.aclose.assert_awaited()
        client.aclose.assert_awaited()


# ---------------------------------------------------------------------------
# Context-window suffix stripping ([1m] / [200k])
# ---------------------------------------------------------------------------

class TestContextWindowSuffixStripping:
    def test_strip_1m_suffix(self):
        import aigw.nine_router_client as mod
        assert mod._strip_context_window_suffix("claude-opus-5[1m]") == "claude-opus-5"

    def test_strip_200k_suffix_case_insensitive(self):
        import aigw.nine_router_client as mod
        assert mod._strip_context_window_suffix("claude-haiku-4-5-20251001[200K]") == "claude-haiku-4-5-20251001"

    def test_no_suffix_unchanged(self):
        import aigw.nine_router_client as mod
        assert mod._strip_context_window_suffix("claude-opus-5") == "claude-opus-5"

    def test_none_returns_none(self):
        import aigw.nine_router_client as mod
        assert mod._strip_context_window_suffix(None) is None

    @pytest.mark.asyncio
    async def test_forward_strips_suffix_before_override_and_forward(self):
        """A model with a [1m] suffix must be normalized before override matching,
        so a rule keyed on the clean name (e.g. "opus") still matches, and the
        suffix is never forwarded to 9router."""
        import aigw.nine_router_client as mod

        resp_ok = _mock_stream_response(200)
        client = _mock_client(response=resp_ok)
        body = b'{"model":"claude-opus-5[1m]","messages":[]}'
        rules = [{"from": "opus", "to": "claude-opus"}]

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body)
            assert isinstance(resp, StreamingResponse)

        sent = client.build_request.call_args_list[0].kwargs["content"]
        assert b'"model":"claude-opus"' in sent
        assert b"[1m]" not in sent

    @pytest.mark.asyncio
    async def test_forward_strips_suffix_when_override_disabled(self):
        """Even with override disabled, the [1m] suffix must be stripped so the
        forwarded body carries the clean model name."""
        import aigw.nine_router_client as mod

        resp_ok = _mock_stream_response(200)
        client = _mock_client(response=resp_ok)
        body = b'{"model":"claude-haiku-4-5-20251001[1m]","messages":[]}'

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(False, [], "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body)
            assert isinstance(resp, StreamingResponse)

        sent = client.build_request.call_args_list[0].kwargs["content"]
        assert b'"model":"claude-haiku-4-5-20251001"' in sent
        assert b"[1m]" not in sent


# ---------------------------------------------------------------------------
# Multi-level override failover
# ---------------------------------------------------------------------------

class TestMultiLevelFailover:
    @pytest.mark.asyncio
    async def test_fails_over_to_next_candidate_on_non_200(self):
        import aigw.nine_router_client as mod

        # First candidate returns 503, second returns 200 streaming.
        resp_fail = _mock_stream_response(503)
        resp_ok = _mock_stream_response(200, chunks=[b'data: {"model":"good-model"}\n\n', b"data: [DONE]\n\n"])
        client = _mock_client(send_side_effect=[resp_fail, resp_ok])

        body = b'{"model":"gpt-4","messages":[]}'
        rules = [{"from": "gpt", "to": ["bad-model", "good-model"]}]

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body)
            assert isinstance(resp, StreamingResponse)
            assert resp.status_code == 200

        # Two send attempts: first rewritten to "bad-model", second to "good-model".
        assert client.send.await_count == 2
        sent_contents = [c.kwargs["content"] for c in client.build_request.call_args_list]
        assert b'"model":"bad-model"' in sent_contents[0]
        assert b'"model":"good-model"' in sent_contents[1]

    @pytest.mark.asyncio
    async def test_all_candidates_failed_returns_last_error(self):
        import aigw.nine_router_client as mod

        resp_fail1 = _mock_stream_response(502)
        resp_fail2 = _mock_stream_response(503)
        client = _mock_client(send_side_effect=[resp_fail1, resp_fail2])

        body = b'{"model":"gpt-4","messages":[]}'
        rules = [{"from": "gpt", "to": ["bad-model", "worse-model"]}]

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body)
            assert isinstance(resp, JSONResponse)
            assert resp.status_code == 503  # last candidate's status

        assert client.send.await_count == 2

    @pytest.mark.asyncio
    async def test_string_rule_still_single_attempt(self):
        import aigw.nine_router_client as mod

        resp_ok = _mock_stream_response(200)
        client = _mock_client(response=resp_ok)
        body = b'{"model":"gpt-4","messages":[]}'
        rules = [{"from": "gpt", "to": "good-model"}]

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body)
            assert isinstance(resp, StreamingResponse)

        assert client.send.await_count == 1
        assert b'"model":"good-model"' in client.build_request.call_args_list[0].kwargs["content"]

    @pytest.mark.asyncio
    async def test_usage_callback_fires_once_for_winning_candidate(self):
        import aigw.nine_router_client as mod

        resp_fail = _mock_stream_response(500)
        resp_ok = _mock_stream_response(
            200,
            chunks=[b'data: {"model":"good-model","usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n', b"data: [DONE]\n\n"],
        )
        client = _mock_client(send_side_effect=[resp_fail, resp_ok])
        body = b'{"model":"gpt-4","messages":[]}'
        rules = [{"from": "gpt", "to": ["bad-model", "good-model"]}]
        seen = {}

        async def on_usage(it, ot, model):
            seen["input"], seen["output"], seen["model"] = it, ot, model

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            req = _mock_request()
            resp = await mod.forward_to_nine_router(req, body, on_usage=on_usage)
            await _drain(resp)

        assert seen == {"input": 5, "output": 3, "model": "good-model"}


class TestOverrideCooldown:
    """Failed override targets are skipped on later requests (aigw.model_cooldown)."""

    async def _forward(self, mod, client, rules):
        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "_get_nine_router_override", AsyncMock(return_value=(True, rules, "auto"))),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=client),
        ):
            return await mod.forward_to_nine_router(_mock_request(), b'{"model":"gpt-4","messages":[]}')

    @pytest.mark.asyncio
    async def test_transient_failure_skips_model_on_next_request(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["bad-model", "good-model"]}]

        client1 = _mock_client(send_side_effect=[_mock_stream_response(503), _mock_stream_response(200)])
        await self._forward(mod, client1, rules)
        assert client1.send.await_count == 2

        # Second request goes straight to good-model.
        client2 = _mock_client(response=_mock_stream_response(200))
        resp = await self._forward(mod, client2, rules)
        assert isinstance(resp, StreamingResponse)
        assert client2.send.await_count == 1
        assert b'"model":"good-model"' in client2.build_request.call_args_list[0].kwargs["content"]

    @pytest.mark.asyncio
    async def test_connect_error_puts_model_on_cooldown(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["bad-model", "good-model"]}]
        client = _mock_client(send_side_effect=[httpx.ConnectError("refused"), _mock_stream_response(200)])
        await self._forward(mod, client, rules)
        assert mod._model_cooldown.remaining("bad-model") > 0
        assert mod._model_cooldown.remaining("good-model") == 0

    @pytest.mark.asyncio
    async def test_pool_timeout_fails_fast_without_cooldown(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["m1", "m2"]}]
        client = _mock_client(send_side_effect=[httpx.PoolTimeout("pool full")])
        resp = await self._forward(mod, client, rules)
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 503
        assert client.send.await_count == 1
        assert mod._model_cooldown.remaining("m1") == 0

    @pytest.mark.asyncio
    async def test_deterministic_4xx_does_not_cool_down(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["m1", "m2"]}]
        client = _mock_client(send_side_effect=[_mock_stream_response(400), _mock_stream_response(200)])
        await self._forward(mod, client, rules)
        assert mod._model_cooldown.remaining("m1") == 0

    @pytest.mark.asyncio
    async def test_retry_after_header_sets_cooldown(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["m1", "m2"]}]
        limited = _mock_stream_response(429, headers={"content-type": "application/json", "retry-after": "120"})
        client = _mock_client(send_side_effect=[limited, _mock_stream_response(200)])
        await self._forward(mod, client, rules)
        assert 100 < mod._model_cooldown.remaining("m1") <= 120

    @pytest.mark.asyncio
    async def test_all_cooling_down_probes_one_model(self):
        import aigw.nine_router_client as mod
        rules = [{"from": "gpt", "to": ["m1", "m2"]}]
        mod._model_cooldown.record_failure("m1", retry_after=60)
        mod._model_cooldown.record_failure("m2", retry_after=30)

        client = _mock_client(response=_mock_stream_response(200))
        resp = await self._forward(mod, client, rules)
        assert isinstance(resp, StreamingResponse)
        assert client.send.await_count == 1
        assert b'"model":"m2"' in client.build_request.call_args_list[0].kwargs["content"]
        # The successful probe clears m2's cooldown.
        assert mod._model_cooldown.remaining("m2") == 0

    @pytest.mark.asyncio
    async def test_single_candidate_never_tracked(self):
        import aigw.nine_router_client as mod
        client = _mock_client(response=_mock_stream_response(503))
        await self._forward(mod, client, [{"from": "gpt", "to": "only-model"}])
        assert mod._model_cooldown.remaining("only-model") == 0

    def test_invalidate_override_cache_clears_cooldown(self):
        import aigw.nine_router_client as mod
        mod._model_cooldown.record_failure("m1")
        mod.invalidate_nine_router_override_cache()
        assert mod._model_cooldown.remaining("m1") == 0


# ---------------------------------------------------------------------------
# fetch_nine_router_models
# ---------------------------------------------------------------------------

def _mock_models_response(status_code: int = 200, payload: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload if payload is not None else {
        "object": "list",
        "data": [
            {"id": "kiro/claude-sonnet-4", "object": "model"},
            {"id": "openai/gpt-5", "object": "model"},
        ],
    }
    return resp


class TestFetchNineRouterModels:
    @pytest.mark.asyncio
    async def test_parses_documented_response_shape(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", ""),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            models = await mod.fetch_nine_router_models()

        assert models == ["kiro/claude-sonnet-4", "openai/gpt-5"]
        mock_client.get.assert_awaited_once_with("http://ninerouter:20128/v1/models", headers={})

    @pytest.mark.asyncio
    async def test_sends_api_key_when_configured(self):
        """A 9router with requireApiKey enabled answers 401 to an anonymous GET,
        which would silently empty the catalog and lock every service account
        out (fail-closed). The key must be sent."""
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch.object(mod, "NINE_ROUTER_API_KEY", "secret-key"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            models = await mod.fetch_nine_router_models()

        assert models == ["kiro/claude-sonnet-4", "openai/gpt-5"]
        mock_client.get.assert_awaited_once_with(
            "http://ninerouter:20128/v1/models",
            headers={"Authorization": "Bearer secret-key"},
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_not_configured(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        with patch.object(mod, "NINE_ROUTER_URL", ""):
            assert await mod.fetch_nine_router_models() == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_non_200(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response(status_code=500))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            assert await mod.fetch_nine_router_models() == []

    @pytest.mark.asyncio
    async def test_never_raises_on_connection_error(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            assert await mod.fetch_nine_router_models() == []

    @pytest.mark.asyncio
    async def test_ignores_malformed_entries(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response(payload={
            "object": "list",
            "data": [
                {"id": "kiro/claude-sonnet-4"},
                {"no_id": "oops"},
                "not-a-dict",
                {"id": ""},
            ],
        }))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            assert await mod.fetch_nine_router_models() == ["kiro/claude-sonnet-4"]

    @pytest.mark.asyncio
    async def test_result_is_cached_until_ttl_expires(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            first = await mod.fetch_nine_router_models()
            second = await mod.fetch_nine_router_models()

        assert first == second
        mock_client.get.assert_awaited_once()  # second call served from cache

    @pytest.mark.asyncio
    async def test_invalidate_forces_refetch(self):
        import aigw.nine_router_client as mod
        mod.invalidate_nine_router_models_cache()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=_mock_models_response())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "NINE_ROUTER_URL", "http://ninerouter:20128"),
            patch("aigw.nine_router_client.httpx.AsyncClient", return_value=mock_client),
        ):
            await mod.fetch_nine_router_models()
            mod.invalidate_nine_router_models_cache()
            await mod.fetch_nine_router_models()

        assert mock_client.get.await_count == 2
