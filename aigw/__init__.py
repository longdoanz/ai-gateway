# -*- coding: utf-8 -*-

"""
AI Gateway - Proxy for Kiro API.

This package provides a modular architecture for proxying
OpenAI API requests to Kiro (AWS CodeWhisperer).

Modules:
    - config: Configuration and constants
    - models: Pydantic models for OpenAI API
    - auth: Kiro authentication manager
    - cache: Model metadata cache
    - utils: Helper utilities
    - converters: OpenAI <-> Kiro format conversion
    - parsers: AWS SSE stream parsers
    - streaming: Response streaming logic
    - http_client: HTTP client with retry logic
    - routes: FastAPI routes
    - exceptions: Exception handlers
"""

# Version is imported from config.py — the single source of truth
# This allows changing the version in only one place
from aigw.config import APP_VERSION as __version__

# Main components for convenient import
from aigw.auth import KiroAuthManager
from aigw.cache import ModelInfoCache
from aigw.http_client import KiroHttpClient
from aigw.routes_openai import router
from aigw.model_resolver import ModelResolver, normalize_model_name, get_model_id_for_kiro

# Configuration
from aigw.config import (
    PROXY_API_KEY,
    REGION,
    HIDDEN_MODELS,
    APP_VERSION,
)

# Models
from aigw.models_openai import (
    ChatCompletionRequest,
    ChatMessage,
    OpenAIModel,
    ModelList,
)

# Converters
from aigw.converters_openai import build_kiro_payload
from aigw.converters_core import (
    extract_text_content,
    merge_adjacent_messages,
)

# Parsers
from aigw.parsers import (
    AwsEventStreamParser,
    parse_bracket_tool_calls,
)

# Streaming
from aigw.streaming_openai import (
    stream_kiro_to_openai,
    collect_stream_response,
)

# Exceptions
from aigw.exceptions import (
    validation_exception_handler,
    sanitize_validation_errors,
)

__all__ = [
    # Version
    "__version__",
    
    # Main classes
    "KiroAuthManager",
    "ModelInfoCache",
    "KiroHttpClient",
    "ModelResolver",
    "router",
    
    # Configuration
    "PROXY_API_KEY",
    "REGION",
    "HIDDEN_MODELS",
    "APP_VERSION",
    
    # Model resolution
    "normalize_model_name",
    "get_model_id_for_kiro",
    
    # Models
    "ChatCompletionRequest",
    "ChatMessage",
    "OpenAIModel",
    "ModelList",
    
    # Converters
    "build_kiro_payload",
    "extract_text_content",
    "merge_adjacent_messages",
    
    # Parsers
    "AwsEventStreamParser",
    "parse_bracket_tool_calls",
    
    # Streaming
    "stream_kiro_to_openai",
    "collect_stream_response",
    
    # Exceptions
    "validation_exception_handler",
    "sanitize_validation_errors",
]