# -*- coding: utf-8 -*-
"""
9Router fallback client.

Forwards OpenAI-compatible requests to a 9router instance when all Kiro
accounts are exhausted (402 quota / all accounts unavailable).

Usage:
    from aigw.nine_router_client import forward_to_nine_router, is_nine_router_enabled

    if is_nine_router_enabled():
        return await forward_to_nine_router(request, body_bytes)
"""

import asyncio
import json
import re
import time
from typing import AsyncIterator, Awaitable, Callable, Optional

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from aigw.config import (
    NINE_ROUTER_API_KEY,
    NINE_ROUTER_MODEL_COOLDOWN_BASE,
    NINE_ROUTER_MODEL_COOLDOWN_MAX,
    NINE_ROUTER_NONSTREAM_READ_TIMEOUT,
    NINE_ROUTER_STREAM_READ_TIMEOUT,
    NINE_ROUTER_URL,
)
from aigw.model_cooldown import ModelCooldown, is_transient_status, parse_retry_after

# ---------------------------------------------------------------------------
# 9router model override — own config (toggle, rules, default), cached in-process
# ---------------------------------------------------------------------------
_nine_router_override_cache: tuple[bool, list[dict], str] | None = None  # (enabled, rules, default_model)


# Cooldown for multi-level override targets that keep failing transiently —
# later requests skip them instead of retrying the broken model every time.
_model_cooldown = ModelCooldown(NINE_ROUTER_MODEL_COOLDOWN_BASE, NINE_ROUTER_MODEL_COOLDOWN_MAX)


def invalidate_nine_router_override_cache() -> None:
    global _nine_router_override_cache
    _nine_router_override_cache = None
    # Rules changed — targets may differ, so stale cooldowns must not linger.
    _model_cooldown.clear()


async def _get_nine_router_override() -> tuple[bool, list[dict], str]:
    """Return (enabled, rules, default_model) from DB config (cached)."""
    global _nine_router_override_cache
    if _nine_router_override_cache is not None:
        return _nine_router_override_cache
    try:
        from aigw.db.engine import async_session_factory
        from aigw.db.repositories import get_config
        async with async_session_factory() as session:
            enabled_raw = await get_config(session, "enable_nine_router_model_override") or "false"
            rules_raw = await get_config(session, "nine_router_model_override_rules") or "[]"
            default_raw = await get_config(session, "nine_router_model_override_default") or "auto"
        import json as _json
        rules = _json.loads(rules_raw) if isinstance(rules_raw, str) else rules_raw
        rules = rules if isinstance(rules, list) else []
        result = (enabled_raw.lower() == "true", rules, default_raw)
    except Exception:
        result = (False, [], "auto")
    _nine_router_override_cache = result
    return result


def _strip_context_window_suffix(model: Optional[str]) -> Optional[str]:
    """Strip a client-side context-window suffix (e.g. ``[1m]``, ``[200k]``).

    Claude Code appends this to the model ID (``claude-opus-5[1m]``) to indicate
    the context window. It is not part of the real model name — 9router's own
    model parser/inference never strips it, so we normalize it here to mirror
    ``aigw.model_resolver.normalize_model_name``.
    """
    if model is None:
        return None
    return re.sub(r"\[\d+[mk]\]$", "", model, flags=re.IGNORECASE)


def _sse_error_frame(path: str, message: str) -> bytes:
    """Build a terminal SSE error event in the dialect of the requested API.

    Args:
        path: Upstream request path — ``/messages`` means Anthropic, anything
            else is treated as OpenAI-compatible.
        message: Human-readable error message.

    Returns:
        One complete SSE frame.
    """
    if "/messages" in path:
        payload = {"type": "error", "error": {"type": "api_error", "message": message}}
        return f"event: error\ndata: {json.dumps(payload)}\n\n".encode()
    payload = {"error": {"message": message, "type": "upstream_error"}}
    return f"data: {json.dumps(payload)}\n\n".encode()


def _rewrite_model_in_body(body: bytes, override_model: str) -> bytes:
    """Replace the 'model' field in a JSON request body. Returns original body on any error."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and "model" in parsed:
            parsed["model"] = override_model
            return json.dumps(parsed, separators=(",", ":")).encode()
    except Exception:
        pass
    return body


# ---------------------------------------------------------------------------
# 9router model catalog — GET /v1/models (no authentication required), used
# by the admin dashboard's model picker (e.g. for Service Account
# allowed_models). Cached in-process for a short TTL since it's a network
# call made from admin UI page loads, not the request hot path.
# ---------------------------------------------------------------------------
_NINE_ROUTER_MODELS_CACHE_TTL = 300  # seconds
_nine_router_models_cache: tuple[list[str], float] | None = None  # (model_ids, fetched_at)


def invalidate_nine_router_models_cache() -> None:
    """Clear the cached 9router model catalog so the next fetch hits the network."""
    global _nine_router_models_cache
    _nine_router_models_cache = None


async def fetch_nine_router_models() -> list[str]:
    """Fetch the list of model ids that 9router can route to.

    Calls 9router's own ``GET /v1/models`` endpoint (source:
    9router/src/app/api/v1/models/route.js), which returns
    ``{"object": "list", "data": [{"id": "<alias>/<model>", ...}]}``
    — e.g. ``"kiro/claude-sonnet-4"``, ``"openai/gpt-5"``. Combo models appear
    as bare ids without an alias prefix (e.g. ``"claude-opus-5"``).

    The endpoint is unauthenticated only while 9router runs with
    ``requireApiKey`` disabled; a deployment that enables it answers 401, so we
    send NINE_ROUTER_API_KEY the same way :func:`forward_to_nine_router` does.
    Results are cached
    in-process for a few minutes to avoid hitting 9router on every admin page
    load.

    Returns:
        List of model-id strings from the ``data[].id`` field. Returns an
        empty list on any failure (network error, non-200, malformed body)
        or when NINE_ROUTER_URL is not configured — this function never raises.
    """
    global _nine_router_models_cache

    now = time.time()
    if _nine_router_models_cache is not None and now - _nine_router_models_cache[1] < _NINE_ROUTER_MODELS_CACHE_TTL:
        return _nine_router_models_cache[0]

    if not NINE_ROUTER_URL:
        return []

    url = f"{NINE_ROUTER_URL.rstrip('/')}/v1/models"
    headers = {}
    if NINE_ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {NINE_ROUTER_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning(f"9router model catalog fetch failed: HTTP {response.status_code}")
            return []
        data = response.json()
        entries = data.get("data", []) if isinstance(data, dict) else []
        model_ids = [entry["id"] for entry in entries if isinstance(entry, dict) and entry.get("id")]
    except Exception as exc:
        logger.warning(f"9router model catalog fetch failed: {exc}")
        return []

    _nine_router_models_cache = (model_ids, now)
    return model_ids


# Headers that must not be forwarded upstream
_HOP_BY_HOP = frozenset({
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "authorization",  # replaced with 9router's own key
    # httpx auto-decompresses response bodies; forwarding content-encoding
    # would make the client decode an already-decoded body.
    "content-encoding",
})


def is_nine_router_enabled() -> bool:
    """Return True when NINE_ROUTER_URL is configured."""
    return bool(NINE_ROUTER_URL)


# Callback signature:
#   (input_tokens, output_tokens, model, *, cache_read_tokens, cache_creation_tokens) -> awaitable
# input_tokens is the FULL prompt (cached included); the cache_* kwargs are the
# cached subset of it, reported for breakdown only — never add them to input.
OnUsage = Callable[..., Awaitable[None]]


def _split_prompt_usage(usage: dict) -> tuple[int, int, int] | None:
    """
    Read a usage object's prompt side as (total prompt, cache read, cache write).

    Anthropic reports the three disjointly (``input_tokens`` is only the
    uncached tail — a few dozen tokens on a cached agent loop), so the total
    is their sum. OpenAI's ``prompt_tokens`` is already the whole prompt, with
    cache hits in ``prompt_tokens_details.cached_tokens``; 9router's translated
    chunks carry both shapes at once, and ``prompt_tokens`` wins when present.

    Args:
        usage: An OpenAI or Anthropic ``usage`` dict.

    Returns:
        (total_prompt, cache_read, cache_creation) — the cache parts are a
        subset of the total — or None when the object carries no prompt-side
        field (e.g. an Anthropic ``message_delta`` with only output).
    """
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    cache_read = usage.get("cache_read_input_tokens", details.get("cached_tokens"))
    cache_creation = usage.get("cache_creation_input_tokens", details.get("cache_creation_tokens"))
    prompt = usage.get("prompt_tokens")
    uncached = usage.get("input_tokens")
    if prompt is None and uncached is None and cache_read is None and cache_creation is None:
        return None
    cache_read = int(cache_read or 0)
    cache_creation = int(cache_creation or 0)
    if prompt is not None:
        return int(prompt), cache_read, cache_creation
    return int(uncached or 0) + cache_read + cache_creation, cache_read, cache_creation


def _accumulate_usage_from_chunk(chunk: str, token_counts: dict, model_box: list) -> None:
    """
    Parse usage/model fields from an SSE chunk (or whole JSON body) and update
    token_counts / model_box in place.

    Mirrors api_key_mode._accumulate_tokens_from_chunk: tolerant of partial /
    malformed JSON, handles both OpenAI (prompt_tokens/completion_tokens) and
    Anthropic (input_tokens/output_tokens, nested under "message").

    ``input`` is the full prompt including cached tokens; ``cache_read`` /
    ``cache_creation`` break out the cached part of it (see
    ``_split_prompt_usage``).
    """
    import json

    def _apply(usage: dict) -> None:
        prompt = _split_prompt_usage(usage)
        if prompt is not None:
            # Overwrite the triple together so the breakdown always matches
            # its total; an all-zero triple only means "not reported".
            if prompt[0] > 0:
                token_counts["input"], token_counts["cache_read"], token_counts["cache_creation"] = prompt
        ot = usage.get("output_tokens") or usage.get("completion_tokens")
        if ot is not None and int(ot) > 0:
            token_counts["output"] = int(ot)

    def _scan(parsed: dict) -> None:
        usage = parsed.get("usage")
        if isinstance(usage, dict):
            _apply(usage)
        msg = parsed.get("message")
        if isinstance(msg, dict):
            if model_box[0] is None and msg.get("model"):
                model_box[0] = msg.get("model")
            msg_usage = msg.get("usage")
            if isinstance(msg_usage, dict):
                _apply(msg_usage)
        if model_box[0] is None and parsed.get("model"):
            model_box[0] = parsed.get("model")

    try:
        # SSE: one or more "data: {...}" lines. Non-streaming: a single JSON body.
        if "data: " in chunk:
            for line in chunk.splitlines():
                line = line.strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        _scan(json.loads(line[6:]))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
        else:
            try:
                _scan(json.loads(chunk))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    except Exception:
        pass


def _build_headers(original_request: Request) -> dict[str, str]:
    """Build forwarding headers, replacing auth with 9router API key."""
    headers = {
        k: v
        for k, v in original_request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    if NINE_ROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {NINE_ROUTER_API_KEY}"
    # Avoid compressed upstream bodies — httpx decompresses them and the
    # content-encoding header is stripped from the proxied response.
    headers["accept-encoding"] = "identity"
    return headers


async def forward_to_nine_router(
    original_request: Request,
    body: bytes,
    path: Optional[str] = None,
    on_usage: Optional[OnUsage] = None,
    apply_override: bool = True,
) -> StreamingResponse | JSONResponse:
    """
    Forward an OpenAI-compatible request to 9router and stream the response back.

    Args:
        original_request: The incoming FastAPI request (for headers and method).
        body: Raw request body bytes.
        path: Override path (default: same as original request path).
        on_usage: Optional async callback invoked once after the response is fully
                  consumed, with (input_tokens, output_tokens, model).  This is
                  *best-effort* — the proxy layer does not delay the client; if the
                  stream is exhausted or an error occurs the callback is still fired
                  with whatever token counts were accumulated (possibly zeroes).
        apply_override: When False, skip the admin-configured 9router model
                  override (see ``_get_nine_router_override``) and forward the
                  request body's model unchanged. Callers that have already
                  validated the requested model against a fixed allowlist
                  (e.g. Service Account enforcement) must pass False here —
                  otherwise the override could silently rewrite the model to
                  one the caller was never granted. Defaults to True so
                  existing callers are unaffected.

    Returns:
        StreamingResponse for streaming requests, JSONResponse for non-streaming.
    """
    if not NINE_ROUTER_URL:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "All Kiro accounts exhausted and 9router fallback is not configured.", "type": "service_unavailable"}},
        )

    target_path = path or original_request.url.path
    target_url = f"{NINE_ROUTER_URL.rstrip('/')}{target_path}"
    if original_request.url.query:
        target_url += f"?{original_request.url.query}"

    # PII guardrail. Runs before the model-override parse below so everything
    # downstream — including the body actually sent and anything 9router logs —
    # sees only surrogates. `pii_vault` is None when the guard is off, in
    # redact mode, or when nothing matched, in which case the response path
    # stays byte-for-byte what it is today.
    from aigw.guardrails import SecretFound, restore_stream, scrub_request

    pii_vault = None
    pii_restore_tool_args = True
    try:
        body, pii_vault, pii_restore_tool_args = await scrub_request(body)
    except SecretFound as exc:
        # Deterministic client error: the same payload will fail identically
        # every time, so this must not be retried or trigger a route cooldown.
        logger.warning(f"PII guard: blocked request carrying {exc.entity_types}")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": (
                        "Request blocked: it contains credential material "
                        f"({', '.join(sorted(set(exc.entity_types)))}). "
                        "Remove the secret and retry."
                    ),
                    "type": "invalid_request_error",
                    "code": "secret_detected",
                }
            },
        )
    except Exception as exc:
        # Fail open for PII: a scrubber bug must not take the gateway down.
        # Secrets fail closed above, and only above — that branch cannot be
        # reached from here.
        logger.error(f"PII guard: scrub failed, forwarding unscrubbed: {exc}")
        pii_vault = None

    # Apply 9router's own model override (independent of Global Model Enforcement).
    # Returns an ordered list of candidate models — a matching multi-level rule
    # yields its targets tried in order; with no matching rule the default (when
    # configured) is the single candidate. `candidates` is a list of
    # Optional[str]: None means "send the original body untouched" (no model key
    # to rewrite).
    enabled, rules, default_model = await _get_nine_router_override()
    original_model: Optional[str] = None
    raw_model: Optional[str] = None
    is_stream = False
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            original_model = parsed.get("model")
            raw_model = original_model
            is_stream = parsed.get("stream") is True
    except Exception:
        pass

    # Strip any client-side context-window suffix (e.g. "claude-opus-5[1m]")
    # before override matching / forwarding, so 9router never sees a model ID
    # with the suffix appended (its own parser/inference does not strip it).
    original_model = _strip_context_window_suffix(original_model)

    if original_model and enabled and apply_override:
        from aigw.model_override import OverrideConfig, resolve_models
        # 9router treats "auto" as a real model name, so a configured default
        # (even "auto") must be enforced via has_default.
        config = OverrideConfig(enabled=True, rules=rules, default_model=default_model, has_default=True)
        candidates: list[Optional[str]] = resolve_models(original_model, config)
        if candidates != [original_model]:
            logger.info(f"9router model override: {original_model!r} → {candidates}")
    else:
        candidates = [original_model]

    # Only a multi-level override has somewhere else to go; its targets come
    # from admin config, which also keeps the cooldown cache bounded.
    use_cooldown = len(candidates) > 1
    if use_cooldown:
        candidates = _model_cooldown.order(candidates)

    headers = _build_headers(original_request)
    logger.info(f"9router fallback: forwarding {original_request.method} {target_path}")

    # Reuse the application-wide pooled client (connection pooling + keep-alive)
    # so a burst of fallbacks does not open one TCP connection — and one file
    # descriptor — per request. Only fall back to a private client when the
    # shared one is unavailable (e.g. called outside the app lifespan / tests),
    # in which case we own it and must close it.
    shared_client = getattr(getattr(original_request, "app", None), "state", None)
    shared_client = getattr(shared_client, "http_client", None)
    if shared_client is not None:
        client = shared_client
        owns_client = False
    else:
        # connect=30s aligned with the shared client timeout in main.py so the
        # fallback path doesn't fail faster than the steady-state path; pool=10s
        # kept short so a genuinely exhausted pool fails fast and the
        # account-manager can move on instead of holding the request for 60s+.
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=10.0))
        owns_client = True

    # Non-streaming: 9router sends nothing until the full completion is ready,
    # so the client's streaming read timeout (between chunks) is too short.
    # Streaming: outlast 9router's stall watchdog so it reports the stall
    # instead of us cutting the connection first.
    request_kwargs: dict = {}
    base = getattr(client, "timeout", None)
    if isinstance(base, httpx.Timeout) and base.read is not None:
        floor = NINE_ROUTER_STREAM_READ_TIMEOUT if is_stream else NINE_ROUTER_NONSTREAM_READ_TIMEOUT
        request_kwargs["timeout"] = httpx.Timeout(
            connect=base.connect,
            read=max(base.read, floor),
            write=base.write,
            pool=base.pool,
        )

    async def _maybe_close_client() -> None:
        # Never close the shared pooled client — only a private one we created.
        if owns_client:
            await client.aclose()

    # Try each candidate in order; on a pre-stream failure advance to the next.
    # Once the upstream accepts a candidate (2xx), stream it back and stop —
    # partial bytes must not be retried.
    last_error: JSONResponse | None = None
    for idx, candidate in enumerate(candidates):
        # `candidate` is usually just the unchanged model: when the override is
        # disabled/absent, `candidates = [original_model]`, so this loop would
        # otherwise parse+re-serialize the whole body just to write back the
        # value it already had (measured ~4.5ms on large payloads). Compare
        # against the *raw* (pre-suffix-strip) model — not `original_model` —
        # because a client-sent suffix like "claude-opus-5[1m]" means a real
        # rewrite is still needed even though `candidate` looks "unchanged".
        if candidate is not None and candidate != raw_model:
            request_body = _rewrite_model_in_body(body, candidate)
        else:
            request_body = body
        try:
            response = await client.send(
                client.build_request(
                    method=original_request.method,
                    url=target_url,
                    headers=headers,
                    content=request_body,
                    **request_kwargs,
                ),
                stream=True,
            )
        except httpx.ConnectError as exc:
            logger.error(f"9router fallback: connection failed to {NINE_ROUTER_URL}: {exc}")
            last_error = JSONResponse(
                status_code=503,
                content={"error": {"message": f"9router fallback unavailable: {exc}", "type": "service_unavailable"}},
            )
        except httpx.PoolTimeout as exc:
            # Our own connection pool is saturated — not the model's fault, and
            # the next candidate would wait on the same pool. Fail fast, no cooldown.
            logger.error(f"9router fallback: connection pool exhausted: {exc}")
            await _maybe_close_client()
            return JSONResponse(
                status_code=503,
                content={"error": {"message": "Gateway is at connection capacity, retry shortly.", "type": "service_unavailable"}},
            )
        except httpx.TimeoutException as exc:
            logger.error(f"9router fallback: timeout: {exc}")
            last_error = JSONResponse(
                status_code=504,
                content={"error": {"message": "9router fallback timed out.", "type": "timeout"}},
            )
        except Exception as exc:
            logger.error(f"9router fallback: unexpected error: {exc}")
            last_error = JSONResponse(
                status_code=502,
                content={"error": {"message": f"9router fallback error: {exc}", "type": "bad_gateway"}},
            )

        if last_error is not None:
            if use_cooldown and candidate is not None:
                _model_cooldown.record_failure(candidate)
            has_more = idx < len(candidates) - 1
            if has_more:
                logger.info(f"9router override failover: {candidate!r} failed, trying next candidate")
                last_error = None  # reset for the next iteration
                continue
            await _maybe_close_client()
            return last_error

        upstream_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in _HOP_BY_HOP
        }

        if response.status_code != 200:
            error_body = await response.aread()
            await response.aclose()
            logger.warning(f"9router fallback returned {response.status_code}: {error_body[:200]}")
            # Deterministic 4xx (bad payload, context overflow...) would fail the
            # same way later, so only transient errors put the model on cooldown.
            if use_cooldown and candidate is not None and is_transient_status(response.status_code):
                _model_cooldown.record_failure(
                    candidate, parse_retry_after(response.headers.get("retry-after"))
                )
            if idx < len(candidates) - 1:
                logger.info(f"9router override failover: {candidate!r} failed ({response.status_code}), trying next candidate")
                continue
            await _maybe_close_client()
            if pii_vault is not None:
                # Upstream errors often quote the offending part of the request
                # back; leaving surrogates in them would confuse the caller.
                from aigw.guardrails import restore_bytes
                error_body = restore_bytes(error_body, pii_vault)
            return JSONResponse(
                status_code=response.status_code,
                content={"error": {"message": error_body.decode("utf-8", errors="replace"), "type": "nine_router_error"}},
            )

        if use_cooldown and candidate is not None:
            _model_cooldown.record_success(candidate)

        is_sse = "event-stream" in response.headers.get("content-type", "")

        async def _stream_and_close() -> AsyncIterator[bytes]:
            token_counts = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
            model_box: list = [None]
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
                    if on_usage is not None and chunk:
                        # Cheap byte-level gate before the UTF-8 decode on the hot path.
                        # OpenAI repeats "model" in every SSE delta, so once we have the
                        # model we only look for "usage" (final chunk) to avoid decoding
                        # every chunk.
                        want_model = model_box[0] is None
                        has_usage = b'"usage"' in chunk
                        if has_usage or (want_model and b'"model"' in chunk):
                            text = chunk.decode("utf-8", errors="ignore")
                            if text:
                                _accumulate_usage_from_chunk(text, token_counts, model_box)
            except httpx.HTTPError as exc:
                # Upstream died mid-stream (read timeout, reset...). Headers are
                # already sent, so the status can't change — but an SSE client
                # should still get a terminal error event, not a silent cut.
                logger.error(f"9router stream interrupted after headers: {exc!r}")
                if is_sse:
                    yield _sse_error_frame(target_path, f"Upstream stream interrupted: {type(exc).__name__}")
            finally:
                # aclose() returns the connection to the shared pool; the client itself
                # is only closed when we privately own it.
                await response.aclose()
                await _maybe_close_client()
                if on_usage is not None:
                    try:
                        await asyncio.shield(
                            on_usage(
                                token_counts["input"],
                                token_counts["output"],
                                model_box[0] or "unknown",
                                cache_read_tokens=token_counts["cache_read"],
                                cache_creation_tokens=token_counts["cache_creation"],
                            )
                        )
                    except Exception as exc:  # never let tracking break the stream
                        logger.debug(f"9router usage callback failed: {exc}")

        # content-length is already stripped by _HOP_BY_HOP, so restoring
        # surrogates (which changes the body length) cannot desync the framing.
        stream = _stream_and_close()
        if pii_vault is not None:
            # A surrogate spans several model tokens, so on an SSE response it
            # arrives split across frames and has to be rejoined at the delta
            # level; a whole JSON body is simply buffered and substituted once.
            content_type = response.headers.get("content-type", "")
            stream = restore_stream(
                stream,
                pii_vault,
                sse="event-stream" in content_type,
                restore_tool_args=pii_restore_tool_args,
            )

        return StreamingResponse(
            stream,
            status_code=response.status_code,
            headers=upstream_headers,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )

    # All candidates exhausted (unreachable in practice — the loop returns within
    # each branch) — safety net returning the last observed error.
    await _maybe_close_client()
    return last_error or JSONResponse(
        status_code=502,
        content={"error": {"message": "9router fallback: all candidates failed.", "type": "bad_gateway"}},
    )
