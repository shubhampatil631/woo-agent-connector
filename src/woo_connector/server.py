"""FastMCP server entrypoint for WooCommerce connector."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("woocommerce-connector")


def main():
    """Main entrypoint for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
