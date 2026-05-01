# -*- coding: utf-8 -*-

"""
Unit tests for DebugLoggerMiddleware.
Tests debug logging initialization at the middleware level.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_scope(path: str) -> dict:
    return {"type": "http", "path": path}


def make_receive(body: bytes = b"") -> AsyncMock:
    return AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})


class TestDebugLoggerMiddlewareEndpointFiltering:
    """Tests for endpoint filtering in middleware."""

    @pytest.mark.asyncio
    async def test_skips_health_endpoint(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/health")
            receive = make_receive()
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_not_called()
                inner_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_skips_docs_endpoint(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/docs")
            receive = make_receive()
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_root_endpoint(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/")
            receive = make_receive()
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_processes_chat_completions_endpoint(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/chat/completions")
            receive = make_receive(b'{"model": "test"}')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()
                mock_logger.log_request_body.assert_called_once_with(b'{"model": "test"}')

    @pytest.mark.asyncio
    async def test_processes_messages_endpoint(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/messages")
            receive = make_receive(b'{"model": "claude"}')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()


class TestDebugLoggerMiddlewareModeHandling:
    """Tests for DEBUG_MODE handling in middleware."""

    @pytest.mark.asyncio
    async def test_skips_when_debug_mode_off(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'off'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/chat/completions")
            receive = make_receive()
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_not_called()
                inner_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_processes_when_debug_mode_errors(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'errors'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/chat/completions")
            receive = make_receive(b'{"test": "data"}')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_when_debug_mode_all(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/messages")
            receive = make_receive(b'{"test": "data"}')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()


class TestDebugLoggerMiddlewareErrorHandling:
    """Tests for error handling in middleware."""

    @pytest.mark.asyncio
    async def test_handles_body_log_error_gracefully(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/chat/completions")
            receive = make_receive(b'{"test": "data"}')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                mock_logger.log_request_body.side_effect = Exception("log error")
                # Should not raise
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()
                inner_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_empty_body(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = make_scope("/v1/chat/completions")
            receive = make_receive(b'')
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_called_once()
                mock_logger.log_request_body.assert_not_called()


class TestDebugLoggerMiddlewareNonHttp:
    """Tests for non-HTTP scope passthrough."""

    @pytest.mark.asyncio
    async def test_passes_through_websocket_scope(self):
        with patch('kiro.debug_middleware.DEBUG_MODE', 'all'):
            from kiro.debug_middleware import DebugLoggerMiddleware

            inner_app = AsyncMock()
            middleware = DebugLoggerMiddleware(app=inner_app)
            scope = {"type": "websocket", "path": "/v1/chat/completions"}
            receive = AsyncMock()
            send = AsyncMock()

            with patch('kiro.debug_logger.debug_logger') as mock_logger:
                await middleware(scope, receive, send)
                mock_logger.prepare_new_request.assert_not_called()
                inner_app.assert_called_once_with(scope, receive, send)


class TestLoggedEndpointsConstant:
    """Tests for LOGGED_ENDPOINTS constant."""

    def test_logged_endpoints_contains_chat_completions(self):
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        assert "/v1/chat/completions" in LOGGED_ENDPOINTS

    def test_logged_endpoints_contains_messages(self):
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        assert "/v1/messages" in LOGGED_ENDPOINTS

    def test_logged_endpoints_is_frozenset(self):
        from kiro.debug_middleware import LOGGED_ENDPOINTS
        assert isinstance(LOGGED_ENDPOINTS, frozenset)
