# -*- coding: utf-8 -*-
"""scrub_request moves large bodies off the event loop (aigw.guardrails)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

import aigw.guardrails as guardrails


def _policy(mode: str = "tokenize"):
    class P:
        pass

    p = P()
    p.mode, p.secret_action, p.restore_tool_args = mode, "warn", True
    return p


def _body(size: int) -> bytes:
    return json.dumps({"model": "m", "messages": [{"role": "user", "content": "x" * size}]}).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("size,offloaded", [(1024, False), (guardrails._OFFLOAD_MIN_BYTES, True)])
async def test_large_bodies_scrub_in_thread(size, offloaded):
    calls = []

    async def fake_to_thread(fn, *args, **kwargs):
        calls.append(fn)
        return fn(*args, **kwargs)

    with (
        patch.object(guardrails, "get_pii_policy", AsyncMock(return_value=_policy())),
        patch.object(guardrails.asyncio, "to_thread", side_effect=fake_to_thread),
    ):
        result = await guardrails.scrub_request(_body(size))

    assert json.loads(result.body)["model"] == "m"
    assert (calls == [guardrails.anonymize_payload]) is offloaded


@pytest.mark.asyncio
async def test_secret_block_still_raises_from_thread():
    policy = _policy()
    policy.secret_action = "block"
    secret = "sk-ant-api03-" + "c" * 93 + "AA"  # same sample as test_guardrails.py
    body = json.dumps({"messages": [{"role": "user", "content": secret + " " + "x" * guardrails._OFFLOAD_MIN_BYTES}]}).encode()
    with patch.object(guardrails, "get_pii_policy", AsyncMock(return_value=policy)):
        with pytest.raises(guardrails.SecretFound):
            await guardrails.scrub_request(body)
