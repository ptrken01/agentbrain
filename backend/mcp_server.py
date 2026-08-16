"""
AgentBrain MCP Server
The shared brain for AI agents.
Deploy with: uvicorn agentbrain.backend.mcp_server:app --host 0.0.0.0 --port 8000
"""

import json
import sqlite3
import os
from datetime import datetime
from typing import Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import asyncio

# Database setup
DB_PATH = os.environ.get("AGENTBRAIN_DB", "agentbrain.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            importance REAL DEFAULT 0.5,
            agent_id TEXT DEFAULT 'anonymous',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            capabilities TEXT DEFAULT '[]',
            endpoint TEXT DEFAULT '',
            reputation REAL DEFAULT 0.5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            domain TEXT DEFAULT 'general',
            source TEXT DEFAULT '',
            confidence REAL DEFAULT 0.8,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
        CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge(domain);
        CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
    """)
    conn.commit()
    return conn

# Initialize database
init_db()

# Create MCP server
app = Server("agentbrain")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="remember",
            description="Store a memory in the shared brain. Semantic searchable by all agents.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The memory content"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                    "importance": {"type": "number", "description": "Importance score 0.0-1.0", "minimum": 0, "maximum": 1},
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="recall",
            description="Search memories by semantic similarity. Returns top-k matches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5},
                    "threshold": {"type": "number", "description": "Similarity threshold", "default": 0.7},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="register_agent",
            description="Register your agent with capabilities and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Agent name"},
                    "description": {"type": "string", "description": "What your agent does"},
                    "capabilities": {"type": "array", "items": {"type": "string"}, "description": "List of capabilities"},
                    "endpoint": {"type": "string", "description": "Agent endpoint URL"},
                },
                "required": ["name", "description", "capabilities"],
            },
        ),
        Tool(
            name="discover_agents",
            description="Find agents by capability, reputation, or keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="add_knowledge",
            description="Add structured knowledge to the shared graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Knowledge content"},
                    "domain": {"type": "string", "description": "Domain/category"},
                    "source": {"type": "string", "description": "Source attribution"},
                    "confidence": {"type": "number", "description": "Confidence score 0.0-1.0", "minimum": 0, "maximum": 1},
                },
                "required": ["content", "domain"],
            },
        ),
        Tool(
            name="query_knowledge",
            description="Query the knowledge graph by domain or keyword.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "domain": {"type": "string", "description": "Filter by domain"},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_context",
            description="Get rich context for any topic. Combines memories + knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to get context for"},
                    "max_tokens": {"type": "integer", "description": "Max context length", "default": 2000},
                },
                "required": ["topic"],
            },
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    conn = get_db()

    if name == "remember":
        content = arguments["content"]
        tags = json.dumps(arguments.get("tags", []))
        importance = arguments.get("importance", 0.5)
        agent_id = arguments.get("agent_id", "anonymous")

        conn.execute(
            "INSERT INTO memories (content, tags, importance, agent_id) VALUES (?, ?, ?, ?)",
            (content, tags, importance, agent_id)
        )
        conn.commit()

        return [TextContent(type="text", text=json.dumps({
            "status": "stored",
            "content": content[:100] + "..." if len(content) > 100 else content
        }))]

    elif name == "recall":
        query = arguments["query"]
        limit = arguments.get("limit", 5)

        # Simple search (in production, use vector similarity)
        cursor = conn.execute(
            "SELECT content, tags, importance, created_at FROM memories "
            "WHERE content LIKE ? OR tags LIKE ? "
            "ORDER BY importance DESC, created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit)
        )
        results = [dict(row) for row in cursor.fetchall()]

        return [TextContent(type="text", text=json.dumps({
            "query": query,
            "results": results,
            "count": len(results)
        }, indent=2))]

    elif name == "register_agent":
        name_val = arguments["name"]
        desc = arguments["description"]
        caps = json.dumps(arguments["capabilities"])
        endpoint = arguments.get("endpoint", "")

        conn.execute(
            "INSERT OR REPLACE INTO agents (name, description, capabilities, endpoint) "
            "VALUES (?, ?, ?, ?)",
            (name_val, desc, caps, endpoint)
        )
        conn.commit()

        return [TextContent(type="text", text=json.dumps({
            "status": "registered",
            "name": name_val,
            "capabilities": arguments["capabilities"]
        }))]

    elif name == "discover_agents":
        query = arguments["query"]
        limit = arguments.get("limit", 10)

        cursor = conn.execute(
            "SELECT name, description, capabilities, reputation FROM agents "
            "WHERE name LIKE ? OR description LIKE ? OR capabilities LIKE ? "
            "ORDER BY reputation DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit)
        )
        results = [dict(row) for row in cursor.fetchall()]

        return [TextContent(type="text", text=json.dumps({
            "query": query,
            "agents": results,
            "count": len(results)
        }, indent=2))]

    elif name == "add_knowledge":
        content = arguments["content"]
        domain = arguments["domain"]
        source = arguments.get("source", "")
        confidence = arguments.get("confidence", 0.8)

        conn.execute(
            "INSERT INTO knowledge (content, domain, source, confidence) VALUES (?, ?, ?, ?)",
            (content, domain, source, confidence)
        )
        conn.commit()

        return [TextContent(type="text", text=json.dumps({
            "status": "added",
            "domain": domain,
            "content": content[:100] + "..." if len(content) > 100 else content
        }))]

    elif name == "query_knowledge":
        query = arguments["query"]
        domain = arguments.get("domain")
        limit = arguments.get("limit", 10)

        if domain:
            cursor = conn.execute(
                "SELECT content, domain, source, confidence FROM knowledge "
                "WHERE domain = ? AND content LIKE ? "
                "ORDER BY confidence DESC LIMIT ?",
                (domain, f"%{query}%", limit)
            )
        else:
            cursor = conn.execute(
                "SELECT content, domain, source, confidence FROM knowledge "
                "WHERE content LIKE ? OR domain LIKE ? "
                "ORDER BY confidence DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
        results = [dict(row) for row in cursor.fetchall()]

        return [TextContent(type="text", text=json.dumps({
            "query": query,
            "results": results,
            "count": len(results)
        }, indent=2))]

    elif name == "get_context":
        topic = arguments["topic"]
        max_tokens = arguments.get("max_tokens", 2000)

        # Get relevant memories
        mem_cursor = conn.execute(
            "SELECT content, importance FROM memories "
            "WHERE content LIKE ? ORDER BY importance DESC LIMIT 5",
            (f"%{topic}%",)
        )
        memories = [dict(row) for row in mem_cursor.fetchall()]

        # Get relevant knowledge
        know_cursor = conn.execute(
            "SELECT content, domain, confidence FROM knowledge "
            "WHERE content LIKE ? OR domain LIKE ? ORDER BY confidence DESC LIMIT 5",
            (f"%{topic}%", f"%{topic}%")
        )
        knowledge = [dict(row) for row in know_cursor.fetchall()]

        context = {
            "topic": topic,
            "memories": memories,
            "knowledge": knowledge,
            "summary": f"Found {len(memories)} memories and {len(knowledge)} knowledge items related to '{topic}'."
        }

        return [TextContent(type="text", text=json.dumps(context, indent=2))]

    else:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
