"""
AgentBrain MCP Server
The shared brain for AI agents.

Any AI agent can plug into AgentBrain via MCP to:
- Store and retrieve memories from the shared knowledge graph
- Discover other agents and their capabilities
- Access shared context and learnings
- Hire other agents for tasks

Usage:
    python -m agentbrain serve
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import chromadb
from chromadb.utils import embedding_functions

# --- Configuration ---
AGENTBRAIN_HOME = Path(os.getenv("AGENTBRAIN_HOME", Path.home() / ".agentbrain"))
AGENTBRAIN_HOME.mkdir(parents=True, exist_ok=True)

CHROMA_PATH = AGENTBRAIN_HOME / "chroma"
DB_PATH = AGENTBRAIN_HOME / "agentbrain.db"

# --- Initialize ChromaDB ---
chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# Collections
memories_collection = chroma_client.get_or_create_collection(
    name="memories",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

agents_collection = chroma_client.get_or_create_collection(
    name="agents",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

knowledge_collection = chroma_client.get_or_create_collection(
    name="knowledge",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

# --- MCP Server ---
app = Server("agentbrain")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools for agents."""
    return [
        Tool(
            name="remember",
            description="Store a memory in the shared brain. Any agent can retrieve it later.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The memory to store"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                    "agent_id": {"type": "string", "description": "ID of the agent storing this memory"},
                    "importance": {"type": "number", "description": "Importance score 0-1 (default 0.5)"},
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="recall",
            description="Retrieve memories from the shared brain. Semantic search across all stored memories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="register_agent",
            description="Register an agent in the AgentBrain registry. Agents can be discovered by others.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Agent name"},
                    "description": {"type": "string", "description": "What this agent does"},
                    "capabilities": {"type": "array", "items": {"type": "string"}, "description": "List of capabilities"},
                    "endpoint": {"type": "string", "description": "Agent endpoint URL (optional)"},
                },
                "required": ["name", "description", "capabilities"]
            }
        ),
        Tool(
            name="discover_agents",
            description="Find agents by capability or description. Discover agents that can help with a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What kind of agent are you looking for?"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="add_knowledge",
            description="Add structured knowledge to the shared brain. Facts, insights, SOPs, learnings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The knowledge to store"},
                    "domain": {"type": "string", "description": "Domain/topic (e.g., 'engineering', 'sales')"},
                    "source": {"type": "string", "description": "Source of this knowledge"},
                    "confidence": {"type": "number", "description": "Confidence score 0-1 (default 0.8)"},
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="query_knowledge",
            description="Query the shared knowledge graph. Get facts, insights, and learnings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What do you want to know?"},
                    "domain": {"type": "string", "description": "Filter by domain"},
                    "limit": {"type": "integer", "description": "Max results (default 5)"},
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_context",
            description="Get rich context about a topic. Combines memories + knowledge for a comprehensive view.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to get context about"},
                    "limit": {"type": "integer", "description": "Max results per source (default 3)"},
                },
                "required": ["topic"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""

    if name == "remember":
        content = arguments["content"]
        tags = arguments.get("tags", [])
        agent_id = arguments.get("agent_id", "anonymous")
        importance = arguments.get("importance", 0.5)

        memory_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(content) % 10000:04d}"

        memories_collection.add(
            documents=[content],
            ids=[memory_id],
            metadatas=[{
                "tags": ",".join(tags),
                "agent_id": agent_id,
                "importance": importance,
                "created_at": datetime.now().isoformat(),
            }]
        )

        return [TextContent(type="text", text=json.dumps({
            "status": "stored",
            "memory_id": memory_id,
            "message": "Memory stored in the shared brain. Any agent can now recall this."
        }))]

    elif name == "recall":
        query = arguments["query"]
        limit = arguments.get("limit", 5)
        tags = arguments.get("tags")

        where = {}
        if tags:
            where = {"tags": {"$in": tags}}

        results = memories_collection.query(
            query_texts=[query],
            n_results=limit,
            where=where if where else None
        )

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            memories.append({
                "content": doc,
                "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
                "agent_id": meta.get("agent_id", "unknown"),
                "importance": meta.get("importance", 0.5),
                "created_at": meta.get("created_at", ""),
            })

        return [TextContent(type="text", text=json.dumps({
            "status": "success",
            "count": len(memories),
            "memories": memories
        }, indent=2))]

    elif name == "register_agent":
        name_val = arguments["name"]
        description = arguments["description"]
        capabilities = arguments["capabilities"]
        endpoint = arguments.get("endpoint", "")

        agent_id = f"agent_{name_val.lower().replace(' ', '_')}_{hash(description) % 10000:04d}"

        agents_collection.add(
            documents=[f"{name_val}. {description}. Capabilities: {', '.join(capabilities)}"],
            ids=[agent_id],
            metadatas=[{
                "name": name_val,
                "description": description,
                "capabilities": ",".join(capabilities),
                "endpoint": endpoint,
                "registered_at": datetime.now().isoformat(),
                "reputation": 0.5,
            }]
        )

        return [TextContent(type="text", text=json.dumps({
            "status": "registered",
            "agent_id": agent_id,
            "message": f"Agent '{name_val}' is now discoverable in the AgentBrain registry."
        }))]

    elif name == "discover_agents":
        query = arguments["query"]
        limit = arguments.get("limit", 5)

        results = agents_collection.query(
            query_texts=[query],
            n_results=limit
        )

        agents = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            agents.append({
                "agent_id": results["ids"][0][i],
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                "capabilities": meta.get("capabilities", "").split(",") if meta.get("capabilities") else [],
                "endpoint": meta.get("endpoint", ""),
                "reputation": meta.get("reputation", 0.5),
            })

        return [TextContent(type="text", text=json.dumps({
            "status": "success",
            "count": len(agents),
            "agents": agents
        }, indent=2))]

    elif name == "add_knowledge":
        content = arguments["content"]
        domain = arguments.get("domain", "general")
        source = arguments.get("source", "unknown")
        confidence = arguments.get("confidence", 0.8)

        knowledge_id = f"knw_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(content) % 10000:04d}"

        knowledge_collection.add(
            documents=[content],
            ids=[knowledge_id],
            metadatas=[{
                "domain": domain,
                "source": source,
                "confidence": confidence,
                "created_at": datetime.now().isoformat(),
            }]
        )

        return [TextContent(type="text", text=json.dumps({
            "status": "stored",
            "knowledge_id": knowledge_id,
            "message": "Knowledge added to the shared brain."
        }))]

    elif name == "query_knowledge":
        query = arguments["query"]
        limit = arguments.get("limit", 5)
        domain = arguments.get("domain")

        where = {}
        if domain:
            where = {"domain": domain}

        results = knowledge_collection.query(
            query_texts=[query],
            n_results=limit,
            where=where if where else None
        )

        knowledge_items = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            knowledge_items.append({
                "content": doc,
                "domain": meta.get("domain", "general"),
                "source": meta.get("source", "unknown"),
                "confidence": meta.get("confidence", 0.8),
                "created_at": meta.get("created_at", ""),
            })

        return [TextContent(type="text", text=json.dumps({
            "status": "success",
            "count": len(knowledge_items),
            "knowledge": knowledge_items
        }, indent=2))]

    elif name == "get_context":
        topic = arguments["topic"]
        limit = arguments.get("limit", 3)

        # Query all three collections
        mem_results = memories_collection.query(query_texts=[topic], n_results=limit)
        knw_results = knowledge_collection.query(query_texts=[topic], n_results=limit)
        agt_results = agents_collection.query(query_texts=[topic], n_results=limit)

        context = {
            "topic": topic,
            "memories": [
                {"content": doc, "metadata": meta}
                for doc, meta in zip(mem_results["documents"][0], mem_results["metadatas"][0])
            ] if mem_results["documents"] else [],
            "knowledge": [
                {"content": doc, "metadata": meta}
                for doc, meta in zip(knw_results["documents"][0], knw_results["metadatas"][0])
            ] if knw_results["documents"] else [],
            "relevant_agents": [
                {"name": meta.get("name"), "description": meta.get("description"), "capabilities": meta.get("capabilities", "").split(",")}
                for doc, meta in zip(agt_results["documents"][0], agt_results["metadatas"][0])
            ] if agt_results["documents"] else [],
        }

        return [TextContent(type="text", text=json.dumps({
            "status": "success",
            "context": context
        }, indent=2))]

    else:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
