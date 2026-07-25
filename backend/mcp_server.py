"""
Laya Healthcare MCP Server
Exposes user profile and policy data as MCP tools so an LLM can look up
customer context before querying the knowledge base.

Run:
    python mcp_server.py          # stdio transport (Claude Desktop / SDK)
    python mcp_server.py --sse    # SSE transport on port 8001
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from mcp.server.fastmcp import FastMCP
from shared import user_client

parser = argparse.ArgumentParser()
parser.add_argument("--sse", action="store_true", help="Run with SSE transport on port 8001")
parser.add_argument("--port", type=int, default=8001)
args, _ = parser.parse_known_args()

mcp = FastMCP(
    "Laya Healthcare User Data",
    host="0.0.0.0",
    port=args.port,
    instructions=(
        "Use these tools to look up a customer's profile, policies, and claims "
        "before answering questions. Always fetch user context first when a user_id "
        "is provided so your answer reflects their specific coverage."
    ),
)


@mcp.tool()
def get_user_profile(user_id: str) -> str:
    """
    Get full profile for a customer: personal details, all policies, and claims history.

    Args:
        user_id: Customer ID in the format USR001, USR042, etc.
    """
    user = user_client.get_user_by_id(user_id)
    if not user:
        return f"No customer found with ID '{user_id}'."
    return json.dumps(user, indent=2)


@mcp.tool()
def get_user_context_summary(user_id: str) -> str:
    """
    Get a concise text summary of a customer's active policies and open claims,
    ready to inject into an LLM prompt.

    Args:
        user_id: Customer ID in the format USR001, USR042, etc.
    """
    context = user_client.build_user_context(user_id)
    if not context:
        return f"No customer found with ID '{user_id}'."
    return context


@mcp.tool()
def search_users(query: str) -> str:
    """
    Search customers by name, email, or policy number prefix.

    Args:
        query: Partial name, email address, or policy number prefix (e.g. "TRV-2026")
    """
    results = user_client.search_users(query, limit=10)
    if not results:
        return f"No customers found matching '{query}'."
    return json.dumps(results, indent=2)


@mcp.tool()
def list_all_users() -> str:
    """
    List all customers with a brief summary (ID, name, active policies, open claims).
    Returns up to 100 records.
    """
    users = user_client.list_users()
    return json.dumps(users, indent=2)


@mcp.tool()
def get_user_claims(user_id: str) -> str:
    """
    Get the full claims history for a customer.

    Args:
        user_id: Customer ID in the format USR001, USR042, etc.
    """
    claims = user_client.get_user_claims(user_id)
    if claims is None:
        return f"No customer found with ID '{user_id}'."
    if not claims:
        return f"Customer {user_id} has no claims on record."
    return json.dumps(claims, indent=2)


@mcp.tool()
def get_user_policies(user_id: str) -> str:
    """
    Get all policies (active and historical) for a customer.

    Args:
        user_id: Customer ID in the format USR001, USR042, etc.
    """
    policies = user_client.get_user_policies(user_id)
    if policies is None:
        return f"No customer found with ID '{user_id}'."
    return json.dumps(policies, indent=2)


if __name__ == "__main__":
    if args.sse:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
