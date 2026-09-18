# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
MCP Tools Support (WebSearch via Kiro MCP API).

Handles the web_search tool that executes on Kiro infrastructure via MCP API:
MCP tool emulation via streaming interception (kiro.streaming_anthropic /
kiro.streaming_openai call into this module when the model invokes the
auto-injected web_search tool).
"""

import json
import time
import uuid
import random
import string
from datetime import datetime
from typing import Dict, Optional, Tuple

import httpx
from loguru import logger

from kiro.tokenizer import count_message_tokens, count_tokens

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# ==================================================================================================
# ID Generation
# ==================================================================================================

def generate_random_id(length: int) -> str:
    """
    Generate random alphanumeric string.
    
    Args:
        length: Length of string to generate
    
    Returns:
        Random string of specified length
    
    Example:
        >>> generate_random_id(22)
        'aBcD1234567890XyZ12345'
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


# ==================================================================================================
# MCP API Functions
# ==================================================================================================

async def call_kiro_mcp_api(
    query: str,
    auth_manager
) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Call Kiro MCP API for web_search.
    
    URL: {auth_manager.q_host}/mcp
    Headers: Authorization, x-amzn-codewhisperer-optout, Content-Type
    Timeout: 60 seconds
    
    Args:
        query: Search query
        auth_manager: KiroAuthManager instance
    
    Returns:
        Tuple of (tool_use_id, results_dict) or (None, None) on error
    
    MCP Request Format:
        {
            "id": "web_search_tooluse_{22random}_{timestamp}_{8random}",
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "web_search",
                "arguments": {"query": "..."}
            }
        }
    
    MCP Response Format:
        {
            "id": "web_search_tooluse_...",
            "jsonrpc": "2.0",
            "result": {
                "content": [{
                    "type": "text",
                    "text": "{\"results\":[...],\"totalResults\":10,\"query\":\"...\"}"
                }],
                "isError": false
            }
        }
    
    CRITICAL: result.content[0].text is a JSON STRING, not a dict!
    """
    # Generate IDs
    random_22 = generate_random_id(22)
    timestamp = int(time.time() * 1000)
    random_8 = generate_random_id(8)
    request_id = f"web_search_tooluse_{random_22}_{timestamp}_{random_8}"
    tool_use_id = f"srvtoolu_{uuid.uuid4().hex[:32]}"
    
    # Build MCP request
    mcp_request = {
        "id": request_id,
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "web_search",
            "arguments": {"query": query}
        }
    }
    
    # Log MCP request
    try:
        mcp_request_json = json.dumps(mcp_request, ensure_ascii=False, indent=2).encode('utf-8')
        if debug_logger:
            debug_logger.log_raw_chunk(b"[MCP REQUEST]\n" + mcp_request_json)
    except Exception as e:
        logger.warning(f"Failed to log MCP request: {e}")
    
    try:
        token = await auth_manager.get_access_token()
        
        # EXACT headers from architecture
        headers = {
            "Authorization": f"Bearer {token}",
            "x-amzn-codewhisperer-optout": "false",
            "Content-Type": "application/json"
        }
        
        mcp_url = f"{auth_manager.q_host}/mcp"
        logger.debug(f"Calling MCP API: {mcp_url}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(mcp_url, json=mcp_request, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"MCP API error: {response.status_code}")
                return None, None
            
            mcp_response = response.json()
            
            # Log MCP response
            try:
                mcp_response_json = json.dumps(mcp_response, ensure_ascii=False, indent=2).encode('utf-8')
                if debug_logger:
                    debug_logger.log_raw_chunk(b"[MCP RESPONSE]\n" + mcp_response_json)
            except Exception as e:
                logger.warning(f"Failed to log MCP response: {e}")
            
            # DEBUG: Log full MCP response to see what we actually got
            # logger.debug(f"MCP API full response: {json.dumps(mcp_response, ensure_ascii=False)}")
            
            if "error" in mcp_response and mcp_response["error"] is not None:
                logger.error(f"MCP API returned error: {mcp_response['error']}")
                return None, None
            
            # Parse results: result.content[0].text is JSON STRING (CRITICAL!)
            result_text = mcp_response.get("result", {}).get("content", [{}])[0].get("text", "{}")
            results = json.loads(result_text)  # Parse JSON string to dict
            
            logger.debug(f"MCP API returned {results.get('totalResults', 0)} results")
            return tool_use_id, results
            
    except httpx.TimeoutException as e:
        logger.error(f"MCP API timeout: {e}")
        return None, None
    except httpx.RequestError as e:
        logger.error(f"MCP API request error: {e}")
        return None, None
    except json.JSONDecodeError as e:
        logger.error(f"MCP API response JSON parse error: {e}")
        return None, None
    except Exception as e:
        logger.error(f"MCP API unexpected exception: {e}", exc_info=True)
        return None, None


def generate_search_summary(query: str, results: Dict) -> str:
    """
    Generate human-readable summary from search results wrapped in XML tags.
    
    Wraps results in <web_search>...</web_search> tags to visually distinguish
    tool output from model's own text. Returns FULL snippets without truncation
    so the model has complete information.
    
    Format per result:
    - Title
    - Published date (converted from milliseconds timestamp)
    - URL
    - Full snippet (no truncation)
    
    Args:
        query: Original search query
        results: Parsed MCP response (dict with "results" key)
    
    Returns:
        Formatted summary text wrapped in XML tags with full snippets
    
    Example:
        '<web_search>\nSearch results for "Python tutorials":\n\n
        1. Title: **Learn Python - Official Tutorial**\n
           Published: 13 Mar 2025 14:23:45\n
           URL: https://python.org/tutorial\n
           [Full snippet text without truncation]\n\n
        </web_search>'
    """
    # Start with opening tag
    summary = f'\n<web_search>\nSearch results for "{query}":\n\n'
    
    if results and "results" in results:
        for i, result in enumerate(results["results"], 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            published_date_ms = result.get("publishedDate")
            
            # Format: Title
            summary += f"{i}. Title: **{title}**\n"
            
            # Format: Published date (convert from milliseconds timestamp)
            if published_date_ms:
                try:
                    # Convert milliseconds to seconds for datetime
                    dt = datetime.fromtimestamp(published_date_ms / 1000)
                    # Format as "13 Mar 2025 14:23:45"
                    date_str = dt.strftime("%d %b %Y %H:%M:%S")
                    summary += f"   Published: {date_str}\n"
                except (ValueError, OSError):
                    # Invalid timestamp - skip date
                    pass
            
            # Format: URL
            if url:
                summary += f"   URL: {url}\n"
            
            # Format: Snippet (NO truncation - model needs full information)
            if snippet:
                summary += f"   {snippet}\n"
            
            summary += "\n"
    else:
        summary += "No results found.\n"
    
    # Close with closing tag
    summary += "</web_search>\n"
    
    return summary

