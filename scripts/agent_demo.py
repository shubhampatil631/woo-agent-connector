"""Agent Studio LLM loop demo connecting an LLM to WooCommerce MCP connector.

Answers canned merchant questions:
1. "Which orders are failed this week?"
2. "What's low on stock in the store?"
3. "Summarize order #1001"

Uses ANTHROPIC_API_KEY from environment if available.
Gracefully demonstrates tool invocation and simulated reasoning if the API key is not present.
"""

import argparse
import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from woo_connector.client import WooClient
from woo_connector.config import Settings
from woo_connector.server import mcp

with contextlib.suppress(Exception):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

console = Console(safe_box=True)

CANNED_QUESTIONS = [
    "Which orders have failed or need merchant attention?",
    "What products are currently low on stock or out of stock?",
    "Summarize order #1001 with items and delivery address.",
]


def get_mock_client() -> WooClient:
    """Create in-process mock client for demo execution."""
    from httpx import ASGITransport, AsyncClient

    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from tests.mock_woo import app as mock_app
    from tests.mock_woo import state as mock_state
    from woo_connector.auth import get_auth_strategy

    config = Settings(
        base_url="https://mock-woocommerce.local",
        consumer_key=mock_state.expected_key,
        consumer_secret=mock_state.expected_secret,
        pii_mode="redacted",
    )
    auth = get_auth_strategy(config)
    transport = ASGITransport(app=mock_app)
    http_client = AsyncClient(
        transport=transport,
        base_url="https://mock-woocommerce.local",
        auth=auth,
    )
    return WooClient(config=config, auth=auth, http_client=http_client)


async def execute_mcp_tool(name: str, arguments: dict[str, Any], client: WooClient) -> Any:
    """Execute tool against FastMCP server with custom client."""
    from unittest.mock import patch

    with patch("woo_connector.server.get_client", return_value=client):
        result = await mcp.call_tool(name, arguments)
        if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[1], dict):
            return result[1]
        if isinstance(result, list) and len(result) > 0 and hasattr(result[0], "text"):
            try:
                return json.loads(result[0].text)
            except Exception:
                return result[0].text
        return result


async def run_live_llm_agent(api_key: str, client: WooClient) -> None:
    """Run interactive loop with Anthropic API."""
    import anthropic

    anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)

    # Convert MCP tools to Anthropic tool definitions
    tools_spec_path = Path(__file__).resolve().parent.parent / "docs" / "mcp-tools.json"
    if tools_spec_path.exists():
        spec = json.loads(tools_spec_path.read_text(encoding="utf-8"))
        tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["inputSchema"],
            }
            for t in spec.get("tools", [])
        ]
    else:
        tools = []

    for idx, question in enumerate(CANNED_QUESTIONS, 1):
        console.print(
            Panel(f"[bold cyan]Question {idx}:[/bold cyan] {question}", border_style="cyan")
        )

        messages = [{"role": "user", "content": question}]
        response = await anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=(
                "You are an assistant for Razorpay Agent Studio connected to WooCommerce. "
                "Use the provided read-only tools to look up orders, inventory, and catalog info. "
                "Be concise, clear, and privacy-conscious."
            ),
            tools=tools,
            messages=messages,
        )

        # Check for tool calls
        for content in response.content:
            if content.type == "tool_use":
                tool_name = content.name
                tool_args = content.input
                console.print(
                    f"  [bold yellow]↳ Tool Call:[/bold yellow] "
                    f"[magenta]{tool_name}[/magenta]({tool_args})"
                )
                tool_result = await execute_mcp_tool(tool_name, tool_args, client)
                res_snippet = json.dumps(tool_result, indent=2)[:300]
                console.print(f"  [bold green]↳ Tool Result:[/bold green] {res_snippet}...")

                # Feed tool result back to LLM
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": json.dumps(tool_result),
                            }
                        ],
                    }
                )

                followup = await anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1024,
                    tools=tools,
                    messages=messages,
                )
                for f_content in followup.content:
                    if f_content.type == "text":
                        console.print(
                            f"\n[bold white]Agent Response:[/bold white]\n{f_content.text}\n"
                        )


async def run_simulated_agent(client: WooClient) -> None:
    """Run deterministic agent simulation when no API key is set."""
    console.print(
        "[dim]No ANTHROPIC_API_KEY detected. Running deterministic tool-use agent "
        "simulation...[/dim]\n"
    )

    scenarios = [
        {
            "question": "Which orders have failed or need merchant attention?",
            "tool": "list_orders",
            "args": {"status": "failed", "page": 1, "per_page": 5},
            "summary": "Found failed orders (#1005) requiring merchant review.",
        },
        {
            "question": "What products are currently low on stock or out of stock?",
            "tool": "list_low_stock",
            "args": {"threshold": 5, "page": 1, "per_page": 5},
            "summary": (
                "2 products need restocking: Leather Laptop Sleeve (SKU: SLEEVE-LTH-01, "
                "Qty: 4) and Wireless Mouse (SKU: MOUSE-WL-BLK, Out of stock)."
            ),
        },
        {
            "question": "Summarize order #1001 with items and delivery address.",
            "tool": "get_order",
            "args": {"order_id": 1001},
            "summary": (
                "Order #1001 is processing. Purchased 2x Leather Laptop Sleeve for "
                "INR 99.98. Shipping to Jane D., Bengaluru, IN "
                "(email: c***@example.com, phone: ***-***-**01)."
            ),
        },
    ]

    for idx, sc in enumerate(scenarios, 1):
        console.print(
            Panel(
                f"[bold cyan]Merchant Query {idx}:[/bold cyan] \"{sc['question']}\"",
                border_style="cyan",
            )
        )
        console.print(
            f"  [bold yellow]↳ Agent Decided Tool Call:[/bold yellow] "
            f"[magenta]{sc['tool']}[/magenta]({sc['args']})"
        )
        result = await execute_mcp_tool(sc["tool"], sc["args"], client)
        console.print(
            f"  [bold green]↳ MCP Tool Response:[/bold green] {json.dumps(result)[:150]}..."
        )
        console.print(f"\n[bold white]Agent Final Response:[/bold white]\n{sc['summary']}\n")


async def main() -> None:
    """Main runner."""
    parser = argparse.ArgumentParser(description="WooCommerce MCP Agent Loop Demo")
    parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    client = get_mock_client()

    console.print(
        Panel(
            "[bold white]Agent Studio Autonomous Query Demonstration[/bold white]\n"
            "[green]3 Canned Merchant Scenarios[/green]",
            title="[bold blue]LLM Tool-Calling Loop[/bold blue]",
            border_style="blue",
        )
    )

    try:
        if api_key:
            await run_live_llm_agent(api_key, client)
        else:
            await run_simulated_agent(client)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
