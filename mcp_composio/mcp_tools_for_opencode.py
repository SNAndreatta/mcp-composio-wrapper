from mcp.server.fastmcp import FastMCP
from composio import Composio
import os
from dotenv import load_dotenv

load_dotenv("/root/mcp-composio/.env")

mcp = FastMCP("composio-wrapper")

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
USER_ID = os.getenv("COMPOSIO_TEST_USER_ID")

composio = Composio(
    api_key=COMPOSIO_API_KEY,

    # Esto se puede poner en algun archivo de configuración por ejemplo
    toolkit_versions={
        "gmail": "20260307_00",
        "googlesheets": "20260309_00",
        "googlecalendar": "20260309_00"
    }
)

@mcp.tool()
def search_composio_tools(query: str):
    """Search available Composio tools."""
    tools = composio.tools.get(user_id=USER_ID, search=query)
    return tools


@mcp.tool()
def execute_composio_tool(slug: str, arguments: dict):
    """Execute a Composio tool."""
    return composio.tools.execute(
        slug,
        user_id=USER_ID,
        arguments=arguments
    )


if __name__ == "__main__":
    mcp.run()