from mcp.server.fastmcp import FastMCP
from composio import Composio
import os
from dotenv import load_dotenv
import time
import json

load_dotenv("/root/mcp-composio/.env")

mcp = FastMCP("composio-wrapper")

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
USER_ID = os.getenv("COMPOSIO_TEST_USER_ID")

composio = Composio(
    api_key=COMPOSIO_API_KEY,
    toolkit_versions={
        "gmail": "20260515_00",
        "googlesheets": "20260512_00",
        "googlecalendar": "20260429_00"
    }
)

@mcp.tool()
def search_composio_tools(query: str):
    """Search available Composio tools and check connection status."""
    tools = composio.tools.get(user_id=USER_ID, search=query)
    
    toolkits = list(set([tool.get('toolkit', tool.get('name', '').split('_')[0].lower()) for tool in tools]))
    
    connection_status = {}
    for toolkit in toolkits:
        try:
            accounts = composio.connected_accounts.list(
                user_ids=[USER_ID],
                toolkit_slugs=[toolkit]
            )
            items = accounts.items
            connection_status[toolkit] = {
                "has_connection": len(items) > 0,
                "connections": [conn.id for conn in items] if items else []
            }
        except Exception as e:
            connection_status[toolkit] = {
                "has_connection": False,
                "error": str(e)
            }
    
    return {
        "tools": tools,
        "connection_status": connection_status,
        "toolkits_needed": toolkits
    }

@mcp.tool()
def ensure_toolkit_connection(toolkit: str):
    """Ensure a toolkit has an active connection, create one if needed."""
    try:
        accounts = composio.connected_accounts.list(
            user_ids=[USER_ID],
            toolkit_slugs=[toolkit]
        )
        items = accounts.items
        
        active = [conn for conn in items if conn.status == 'ACTIVE']
        if active:
            return {
                "status": "active",
                "connection_id": active[0].id,
                "message": f"Active connection found for {toolkit}"
            }
        
        if items:
            conn = items[0]
            return {
                "status": conn.status,
                "connection_id": conn.id,
                "message": f"Connection for {toolkit} is in state: {conn.status}"
            }
        
        auth_configs = composio.auth_configs.list()
        auth_config_id = None
        for ac in auth_configs.items:
            ac_name = ac.name or ac.toolkit or ''
            if toolkit.lower() in ac_name.lower():
                auth_config_id = ac.id
                break
        
        if not auth_config_id:
            return {
                "status": "error",
                "error": f"No auth config found for toolkit: {toolkit}",
                "message": f"No auth config found for {toolkit}. Please configure it in the Composio dashboard first."
            }
        
        connection = composio.connected_accounts.initiate(
            user_id=USER_ID,
            auth_config_id=auth_config_id
        )
        
        redirect_url = connection.redirect_url
        
        return {
            "status": "created",
            "connection_id": connection.id,
            "auth_url": redirect_url,
            "message": f"New connection created for {toolkit}",
            "instructions": "If auth_url is provided, please visit it to complete authentication"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to establish connection for {toolkit}"
        }

@mcp.tool()
def check_connection_status(toolkit: str):
    """Check the status of a toolkit connection."""
    try:
        accounts = composio.connected_accounts.list(
            user_ids=[USER_ID],
            toolkit_slugs=[toolkit]
        )
        items = accounts.items
        
        if not items:
            return {
                "status": "no_connection",
                "message": f"No connection found for {toolkit}"
            }
        
        conn = items[0]
        conn_status = conn.status
        is_active = conn_status == 'ACTIVE'
        
        return {
            "status": "active" if is_active else "inactive",
            "connection_id": conn.id,
            "is_active": is_active,
            "raw_status": conn_status,
            "message": f"Connection for {toolkit} is {'active' if is_active else 'inactive'} (status: {conn_status})"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

def extract_toolkit_from_slug(slug: str):
    """Extract toolkit name from tool slug."""
    parts = slug.split('_')
    if len(parts) > 0:
        return parts[0].lower()
    return slug.lower()

@mcp.tool()
def execute_composio_tool(slug: str, arguments: dict, auto_connect: bool = True):
    """Execute a Composio tool with automatic connection handling."""
    try:
        toolkit = extract_toolkit_from_slug(slug)
        
        if auto_connect:
            connection_result = ensure_toolkit_connection(toolkit)
            
            if connection_result["status"] == "error":
                return {
                    "success": False,
                    "error": f"Failed to establish connection: {connection_result['error']}",
                    "connection_result": connection_result
                }
            
            if connection_result.get("auth_url"):
                return {
                    "success": False,
                    "error": "Authentication required",
                    "auth_url": connection_result["auth_url"],
                    "message": "Please visit the auth_url to complete authentication, then try again"
                }
        
        status = check_connection_status(toolkit)
        if status["status"] != "active":
            return {
                "success": False,
                "error": f"No active connection for {toolkit}",
                "connection_status": status,
                "suggestion": "Try running ensure_toolkit_connection() first"
            }
        
        result = composio.tools.execute(
            slug,
            user_id=USER_ID,
            arguments=arguments,
            connected_account_id=status["connection_id"]
        )
        
        return {
            "success": True,
            "result": result,
            "toolkit": toolkit,
            "connection_id": status["connection_id"]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def execute_with_connection_check(slug: str, arguments: dict):
    """Execute a tool with comprehensive connection verification."""
    
    toolkit = extract_toolkit_from_slug(slug)
    
    connection_result = ensure_toolkit_connection(toolkit)
    
    if connection_result["status"] == "error":
        return {
            "success": False,
            "error": "Connection failed",
            "details": connection_result
        }
    
    if connection_result.get("auth_url"):
        return {
            "success": False,
            "error": "Authentication required",
            "auth_url": connection_result["auth_url"],
            "message": "Complete authentication at the provided URL and try again"
        }
    
    max_retries = 3
    status = None
    for attempt in range(max_retries):
        status = check_connection_status(toolkit)
        
        if status["status"] == "active":
            break
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    if status["status"] != "active":
        return {
            "success": False,
            "error": f"Connection not active after {max_retries} attempts",
            "status": status
        }
    
    try:
        result = composio.tools.execute(
            slug,
            user_id=USER_ID,
            arguments=arguments,
            connected_account_id=status["connection_id"]
        )
        
        return {
            "success": True,
            "result": result,
            "toolkit": toolkit,
            "connection_verified": True
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        }

@mcp.tool()
def get_tool_details(slug: str):
    """Get detailed information about a specific tool."""
    tools = composio.tools.get(user_id=USER_ID, search=slug)
    
    exact_tool = next((tool for tool in tools if tool.get('name') == slug or tool.get('slug') == slug), None)
    
    if exact_tool:
        return {
            "found": True,
            "tool": exact_tool,
            "toolkit": extract_toolkit_from_slug(slug)
        }
    
    return {
        "found": False,
        "partial_matches": tools,
        "searched_slug": slug
    }

if __name__ == "__main__":
    mcp.run()
