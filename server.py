"""
AgentBrain MCP Server — Shared Context Layer for AI Agents
Gated by subscription tier via Auth Service
"""
import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:8000")

app = Server("agentbrain")

# In-memory storage for memories (would be ChromaDB in production)
memories_db = {}
knowledge_db = {}
agents_db = {}

async def verify_api_key(api_key: str) -> dict:
    """Verify API key with auth service and return user info"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/auth/limits",
                headers={"X-API-Key": api_key},
                timeout=5
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return {"tier": "free", "max_memories": 1000, "max_api_calls_per_day": 100, "features": ["basic_search"]}

def check_feature_access(user_tier: str, feature: str) -> bool:
    """Check if a tier has access to a feature"""
    tier_features = {
        "free": ["basic_search", "remember", "recall"],
        "pro": ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph"],
        "team": ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph", "team_brain", "marketplace", "audit_trail", "register_agent"]
    }
    return feature in tier_features.get(user_tier, [])

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="remember",
            description="Store a memory in your shared brain",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "description": "Your AgentBrain API key"},
                    "content": {"type": "string", "description": "What to remember"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"}
                },
                "required": ["api_key", "content"]
            }
        ),
        Tool(
            name="recall",
            description="Recall memories from your shared brain",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "description": "Your AgentBrain API key"},
                    "query": {"type": "string", "description": "What to search for"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"}
                },
                "required": ["api_key", "query"]
            }
        ),
        Tool(
            name="register_agent",
            description="Register an agent in the marketplace (Team only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "agent_name": {"type": "string"},
                    "agent_description": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["api_key", "agent_name", "agent_description"]
            }
        ),
        Tool(
            name="discover_agents",
            description="Discover agents in the marketplace (Pro+)",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "capability": {"type": "string", "description": "Filter by capability"}
                },
                "required": ["api_key"]
            }
        ),
        Tool(
            name="add_knowledge",
            description="Add to the knowledge graph (Pro+)",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "concept": {"type": "string"},
                    "definition": {"type": "string"},
                    "related": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["api_key", "concept", "definition"]
            }
        ),
        Tool(
            name="query_knowledge",
            description="Query the knowledge graph (Pro+)",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "query": {"type": "string"}
                },
                "required": ["api_key", "query"]
            }
        ),
        Tool(
            name="get_context",
            description="Get context for a specific task",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_key": {"type": "string"},
                    "task": {"type": "string"},
                    "depth": {"type": "string", "enum": ["shallow", "deep"], "description": "Pro+ for deep"}
                },
                "required": ["api_key", "task"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    api_key = arguments.get("api_key", "")
    user = await verify_api_key(api_key)
    tier = user.get("tier", "free")

    # Check feature access
    feature_map = {
        "remember": "remember",
        "recall": "recall",
        "register_agent": "register_agent",
        "discover_agents": "agent_discovery",
        "add_knowledge": "knowledge_graph",
        "query_knowledge": "knowledge_graph",
        "get_context": "basic_search"
    }

    required_feature = feature_map.get(name)
    if required_feature and not check_feature_access(tier, required_feature):
        return [TextContent(
            type="text",
            text=f"🔒 Upgrade required. The '{name}' feature requires Pro or Team plan.\n"
                 f"Your tier: {tier}\n"
                 f"Upgrade at: https://brain.autoincomesys.com/#pricing"
        )]

    # Route to handler
    if name == "remember":
        return await handle_remember(arguments, user)
    elif name == "recall":
        return await handle_recall(arguments, user)
    elif name == "register_agent":
        return await handle_register_agent(arguments, user)
    elif name == "discover_agents":
        return await handle_discover_agents(arguments, user)
    elif name == "add_knowledge":
        return await handle_add_knowledge(arguments, user)
    elif name == "query_knowledge":
        return await handle_query_knowledge(arguments, user)
    elif name == "get_context":
        return await handle_get_context(arguments, user)

    return [TextContent(type="text", text=f"Unknown tool: {name}")]

async def handle_remember(args: dict, user: dict) -> list[TextContent]:
    content = args.get("content", "")
    tags = args.get("tags", [])
    tier = user.get("tier", "free")
    max_mem = user.get("max_memories", 1000)

    # Count existing memories
    user_memories = [m for m in memories_db.values() if m.get("tier") == tier]
    if len(user_memories) >= max_mem:
        return [TextContent(
            type="text",
            text=f"⚠️ Memory limit reached ({max_mem}/{max_mem}). Upgrade to Pro for 50K memories.\n"
                 f"Upgrade: https://brain.autoincomesys.com/#pricing"
        )]

    mem_id = f"mem_{int(time.time() * 1000)}"
    memories_db[mem_id] = {
        "content": content,
        "tags": tags,
        "tier": tier,
        "created_at": datetime.now().isoformat()
    }

    return [TextContent(
        type="text",
        text=f"✅ Memory saved! ({len(user_memories)+1}/{max_mem} used)\nID: {mem_id}"
    )]

async def handle_recall(args: dict, user: dict) -> list[TextContent]:
    query = args.get("query", "")
    limit = args.get("limit", 10)
    tier = user.get("tier", "free")

    # Free tier: basic search, Pro+: advanced (semantic)
    results = []
    for mem_id, mem in memories_db.items():
        if query.lower() in mem["content"].lower():
            results.append({"id": mem_id, "content": mem["content"], "tags": mem.get("tags", [])})
        if len(results) >= limit:
            break

    if not results:
        return [TextContent(type="text", text="No memories found matching your query.")]

    text = f"🔍 Found {len(results)} memories:\n\n"
    for r in results:
        text += f"- [{r['id']}] {r['content'][:100]}...\n"

    if tier == "free":
        text += "\n💡 Pro tip: Upgrade for advanced semantic search and context packs."

    return [TextContent(type="text", text=text)]

async def handle_register_agent(args: dict, user: dict) -> list[TextContent]:
    name = args.get("agent_name", "")
    desc = args.get("agent_description", "")
    caps = args.get("capabilities", [])

    agent_id = f"agent_{int(time.time() * 1000)}"
    agents_db[agent_id] = {
        "name": name,
        "description": desc,
        "capabilities": caps,
        "registered_at": datetime.now().isoformat()
    }

    return [TextContent(
        type="text",
        text=f"✅ Agent '{name}' registered!\nID: {agent_id}\n"
             f"Visible in marketplace at: https://brain.autoincomesys.com/marketplace"
    )]

async def handle_discover_agents(args: dict, user: dict) -> list[TextContent]:
    capability = args.get("capability")

    results = []
    for agent_id, agent in agents_db.items():
        if capability is None or capability in agent.get("capabilities", []):
            results.append({"id": agent_id, **agent})

    if not results:
        return [TextContent(type="text", text="No agents found.")]

    text = f"🤖 Found {len(results)} agents:\n\n"
    for r in results:
        text += f"- {r['name']}: {r['description']}\n"

    return [TextContent(type="text", text=text)]

async def handle_add_knowledge(args: dict, user: dict) -> list[TextContent]:
    concept = args.get("concept", "")
    definition = args.get("definition", "")
    related = args.get("related", [])

    knowledge_db[concept] = {
        "definition": definition,
        "related": related,
        "added_at": datetime.now().isoformat()
    }

    return [TextContent(
        type="text",
        text=f"✅ Knowledge added: {concept}\nRelated: {', '.join(related) if related else 'none'}"
    )]

async def handle_query_knowledge(args: dict, user: dict) -> list[TextContent]:
    query = args.get("query", "")

    results = []
    for concept, data in knowledge_db.items():
        if query.lower() in concept.lower() or query.lower() in data["definition"].lower():
            results.append({"concept": concept, **data})

    if not results:
        return [TextContent(type="text", text="No knowledge found matching query.")]

    text = f"📚 Knowledge results:\n\n"
    for r in results:
        text += f"- {r['concept']}: {r['definition'][:150]}\n"

    return [TextContent(type="text", text=text)]

async def handle_get_context(args: dict, user: dict) -> list[TextContent]:
    task = args.get("task", "")
    depth = args.get("depth", "shallow")
    tier = user.get("tier", "free")

    if depth == "deep" and tier == "free":
        return [TextContent(
            type="text",
            text="🔒 Deep context requires Pro plan. Upgrade at: https://brain.autoincomesys.com/#pricing"
        )]

    # Find relevant memories
    context_parts = []
    for mem_id, mem in memories_db.items():
        if any(word in mem["content"].lower() for word in task.lower().split()):
            context_parts.append(mem["content"])

    if not context_parts:
        return [TextContent(type="text", text="No relevant context found for this task.")]

    text = f"🧠 Context for '{task}':\n\n"
    for part in context_parts[:5]:
        text += f"- {part[:200]}\n\n"

    return [TextContent(type="text", text=text)]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
