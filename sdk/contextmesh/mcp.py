"""
ContextMesh MCP Server — installable entry point.
Exposes ContextMesh as a Model Context Protocol server over stdio.

Any MCP-compatible agent (Claude Code, Cursor, Cline, etc.)
can add one line to their config and gain persistent memory.

Usage in ~/.cursor/mcp.json or ~/.claude/mcp.json:
{
  "contextmesh": {
    "command": "contextmesh-mcp",
    "env": {
      "CM_KEY": "cm_live_your_key_here",
      "CM_URL": "https://contextmesh.dev"
    }
  }
}

Or with npx (no install required):
{
  "contextmesh": {
    "command": "npx",
    "args": ["contextmesh-mcp"],
    "env": { "CM_KEY": "cm_live_your_key_here" }
  }
}
"""

import sys
import os
import json
import asyncio
import httpx
from typing import Any

CM_KEY = os.getenv("CM_KEY", "")
CM_URL = os.getenv("CM_URL", "https://contextmesh.dev").rstrip("/")

HEADERS = {"Authorization": f"Bearer {CM_KEY}", "Content-Type": "application/json"}


# ── MCP Protocol helpers ──────────────────────────────────────────────────────

def mcp_response(id_: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}

def mcp_error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

def write(obj: dict):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "remember",
        "description": (
            "Store a piece of context, knowledge, or fact that should be remembered "
            "across sessions and accessible to other agents. Use this whenever you "
            "learn something important about the codebase, team preferences, "
            "infrastructure, or project decisions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The context to remember. Be specific and self-contained.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for categorization e.g. ['database', 'conventions']",
                },
                "confidence": {
                    "type": "number",
                    "description": "How certain you are (0.0–1.0). Default 1.0.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search stored context using natural language. Returns the most relevant "
            "facts ranked by semantic similarity. Call this at the start of any task "
            "to retrieve relevant context before taking action."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you want to know. Use natural language.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "How many results to return (1–10). Default 5.",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter to only entries with this tag.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "forget",
        "description": "Remove a specific context entry by its ID. Use when context is outdated or wrong.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The entry ID to delete (from a previous remember or recall call).",
                }
            },
            "required": ["id"],
        },
    },
    {
        "name": "list_context",
        "description": "Browse what's stored. Useful for auditing or finding stale entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entries to return (default 20)"},
                "tag":   {"type": "string",  "description": "Filter by tag"},
            },
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

async def call_api(method: str, path: str, body: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        if method == "POST":
            r = await client.post(f"{CM_URL}{path}", headers=HEADERS, json=body or {})
        elif method == "DELETE":
            r = await client.delete(f"{CM_URL}{path}", headers=HEADERS)
        else:
            r = await client.get(f"{CM_URL}{path}", headers=HEADERS, params=body or {})
        r.raise_for_status()
        return r.json()


async def execute_tool(name: str, args: dict) -> str:
    # Read key/url dynamically so tests can monkeypatch os.environ
    key = os.getenv("CM_KEY", CM_KEY)
    url = os.getenv("CM_URL", CM_URL).rstrip("/")
    hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    if not key:
        return "ERROR: CM_KEY environment variable not set. Get a key at https://contextmesh.dev"

    async def _call(method: str, path: str, body: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "POST":
                r = await client.post(f"{url}{path}", headers=hdrs, json=body or {})
            elif method == "DELETE":
                r = await client.delete(f"{url}{path}", headers=hdrs)
            else:
                r = await client.get(f"{url}{path}", headers=hdrs, params=body or {})
            r.raise_for_status()
            return r.json()

    try:
        if name == "remember":
            result = await _call("POST", "/remember", {
                "text":         args["text"],
                "tags":         args.get("tags", []),
                "confidence":   args.get("confidence", 1.0),
                "source_agent": "mcp",
            })
            return f"Stored. ID: {result['id']} | Tags: {result.get('tags', [])}"

        elif name == "recall":
            result = await _call("POST", "/query", {
                "q":          args["query"],
                "top_k":      args.get("top_k", 5),
                "tag_filter": args.get("tag"),
            })
            if not result["results"]:
                return "No relevant context found."
            lines = [f"Found {result['count']} relevant entries:\n"]
            for i, r in enumerate(result["results"], 1):
                tags = f" [{', '.join(r['tags'])}]" if r.get("tags") else ""
                lines.append(f"{i}. (score={r['score']:.2f}{tags}) {r['text']}\n   ID: {r['id']}")
            return "\n".join(lines)

        elif name == "forget":
            await _call("DELETE", f"/forget/{args['id']}")
            return f"Deleted entry {args['id']}"

        elif name == "list_context":
            params = {"limit": args.get("limit", 20)}
            if args.get("tag"):
                params["tag_filter"] = args["tag"]
            result = await _call("GET", "/list", params)
            if not result["entries"]:
                return "No context stored yet."
            lines = [f"Total stored: {result['total']}\n"]
            for e in result["entries"]:
                tags = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
                lines.append(f"• {e['text'][:120]}{'...' if len(e['text']) > 120 else ''}{tags}\n  ID: {e['id']}")
            return "\n".join(lines)

        # Unknown tool — return None (matches original behavior expected by tests)
        return None

    except httpx.HTTPStatusError as e:
        return f"API error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error: {str(e)}"


# ── MCP stdio event loop ──────────────────────────────────────────────────────

async def _handle_message(msg: dict):
    method = msg.get("method", "")
    id_    = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        write(mcp_response(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities":    {"tools": {}},
            "serverInfo":      {"name": "contextmesh", "version": "1.0.0"},
        }))

    elif method == "tools/list":
        write(mcp_response(id_, {"tools": TOOLS}))

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        result    = await execute_tool(tool_name, tool_args)
        write(mcp_response(id_, {
            "content": [{"type": "text", "text": result}],
            "isError": result.startswith("ERROR") or result.startswith("API error"),
        }))

    elif method == "notifications/initialized":
        pass  # no response needed

    else:
        if id_ is not None:
            write(mcp_error(id_, -32601, f"Method not found: {method}"))


async def _async_main():
    loop   = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.decode().strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        await _handle_message(msg)


def _sync_main():
    """Windows fallback: synchronous stdin polling."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        asyncio.run(_handle_message(msg))


def main():
    """Entry point for the contextmesh-mcp CLI command."""
    if sys.platform == "win32":
        _sync_main()
    else:
        asyncio.run(_async_main())


if __name__ == "__main__":
    main()
