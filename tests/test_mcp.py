"""
Tests for the MCP server tool execution logic.
Mocks httpx so no real API calls are made.
"""

import pytest
import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestMCPTools:
    """Test each MCP tool's execute_tool function."""

    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("CM_KEY", "cm_live_test_key")
        monkeypatch.setenv("CM_URL", "https://api.contextmesh.dev")

    @pytest.mark.asyncio
    async def test_remember_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "e-001", "status": "stored", "tags": ["db"]}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__  = AsyncMock(return_value=False)
            from mcp_server import execute_tool
            result = await execute_tool("remember", {"text": "prod DB is postgres 15", "tags": ["db"]})

        assert "e-001" in result
        assert "Stored" in result

    @pytest.mark.asyncio
    async def test_recall_with_results(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "count": 1,
            "results": [{"id": "e-001", "text": "postgres 15 on AWS", "score": 0.92, "tags": ["db"]}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__  = AsyncMock(return_value=False)
            from mcp_server import execute_tool
            result = await execute_tool("recall", {"query": "what database are we using?"})

        assert "postgres 15" in result
        assert "0.92" in result

    @pytest.mark.asyncio
    async def test_recall_no_results(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"count": 0, "results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__  = AsyncMock(return_value=False)
            from mcp_server import execute_tool
            result = await execute_tool("recall", {"query": "nothing matches this"})

        assert "No relevant context" in result

    @pytest.mark.asyncio
    async def test_forget_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "e-001", "status": "deleted"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.delete.return_value = mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__  = AsyncMock(return_value=False)
            from mcp_server import execute_tool
            result = await execute_tool("forget", {"id": "e-001"})

        assert "e-001" in result
        assert "Deleted" in result

    @pytest.mark.asyncio
    async def test_no_key_returns_error(self, monkeypatch):
        monkeypatch.setenv("CM_KEY", "")
        from mcp_server import execute_tool
        result = await execute_tool("remember", {"text": "test"})
        assert "ERROR" in result
        assert "CM_KEY" in result

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_none(self):
        from mcp_server import execute_tool
        result = await execute_tool("nonexistent_tool", {})
        assert result is None


class TestMCPProtocol:
    """Test MCP JSON-RPC response formatting."""

    def test_mcp_response_format(self):
        from mcp_server import mcp_response
        r = mcp_response(1, {"tools": []})
        assert r["jsonrpc"] == "2.0"
        assert r["id"]      == 1
        assert "result"     in r

    def test_mcp_error_format(self):
        from mcp_server import mcp_error
        e = mcp_error(1, -32601, "Method not found")
        assert e["jsonrpc"] == "2.0"
        assert e["id"]      == 1
        assert e["error"]["code"]    == -32601
        assert e["error"]["message"] == "Method not found"

    def test_tools_list_has_4_tools(self):
        from mcp_server import TOOLS
        assert len(TOOLS) == 4
        names = [t["name"] for t in TOOLS]
        assert "remember"     in names
        assert "recall"       in names
        assert "forget"       in names
        assert "list_context" in names

    def test_tools_have_required_fields(self):
        from mcp_server import TOOLS
        for tool in TOOLS:
            assert "name"        in tool
            assert "description" in tool
            assert "inputSchema" in tool
