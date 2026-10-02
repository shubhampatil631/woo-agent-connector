"""Export machine-readable MCP tool specification to docs/mcp-tools.json.

Introspects registered FastMCP tools to ensure the spec never drifts from code.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from woo_connector.server import mcp

DOCS_DIR = Path(__file__).parent.parent / "docs"
OUTPUT_FILE = DOCS_DIR / "mcp-tools.json"

ERROR_CODES = [
    {
        "code": "AUTH_FAILED",
        "description": "API credentials invalid or insufficient permissions",
        "retryable": False,
    },
    {
        "code": "NOT_FOUND",
        "description": "Requested order, product, or resource does not exist",
        "retryable": False,
    },
    {
        "code": "RATE_LIMITED",
        "description": "WooCommerce rate limits reached after maximum retries exhausted",
        "retryable": True,
    },
    {
        "code": "UPSTREAM_ERROR",
        "description": "WooCommerce or WordPress server returned 5xx status or network timeout",
        "retryable": True,
    },
    {
        "code": "INVALID_INPUT",
        "description": "Malformed input parameters (invalid date format, negative page numbers)",
        "retryable": False,
    },
]


def python_type_to_json_type(t: Any) -> str:
    if t in (int,):
        return "integer"
    if t in (float,):
        return "number"
    if t in (bool,):
        return "boolean"
    if t in (list, list[Any]):
        return "array"
    if t in (dict, dict[str, Any]):
        return "object"
    return "string"


async def export_spec() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    tools_spec = []
    # Introspect MCP tools registered on FastMCP
    registered_tools = await mcp.list_tools()

    for tool in registered_tools:
        name = tool.name
        description = tool.description or ""
        input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}

        tool_entry = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "outputSchema": {
                "type": "object",
                "description": "Structured domain model or paginated result dictionary",
            },
            "errorCodes": ERROR_CODES,
        }
        tools_spec.append(tool_entry)

    spec = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "WooCommerce Agent Studio Connector MCP Specification",
        "version": "0.1.0",
        "description": (
            "Machine-readable specification for read-only WooCommerce Agent Studio tools"
        ),
        "transport": ["stdio", "http/sse"],
        "tools": tools_spec,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"Successfully exported {len(tools_spec)} MCP tool specifications to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(export_spec())
