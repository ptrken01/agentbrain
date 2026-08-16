"""
AgentBrain REST API Server
Deploy with: uvicorn agentbrain.backend.api:app --host 0.0.0.0 --port 8000
"""

import json
import sqlite3
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="AgentBrain API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """)
    conn.commit()
    return conn

init_db()

# Models
class MemoryCreate(BaseModel):
    content: str
    tags: List[str] = []
    importance: float = 0.5
    agent_id: str = "anonymous"

class MemorySearch(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.7

class AgentCreate(BaseModel):
    name: str
    description: str
    capabilities: List[str]
    endpoint: str = ""

class AgentSearch(BaseModel):
    query: str
    limit: int = 10

class KnowledgeCreate(BaseModel):
    content: str
    domain: str
    source: str = ""
    confidence: float = 0.8

class KnowledgeSearch(BaseModel):
    query: str
    domain: Optional[str] = None
    limit: int = 10

class ContextRequest(BaseModel):
    topic: str
    max_tokens: int = 2000

# Routes
@app.get("/")
async def root():
    return {
        "name": "AgentBrain",
        "version": "1.0.0",
        "status": "live",
        "docs": "/docs",
        "mcp_endpoint": "/mcp"
    }

@app.get("/api/status")
async def status():
    conn = get_db()
    mem_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    know_count = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]

    return {
        "status": "live",
        "stats": {
            "memories_stored": mem_count,
            "agents_registered": agent_count,
            "knowledge_nodes": know_count
        }
    }

@app.post("/api/memories")
async def create_memory(memory: MemoryCreate):
    conn = get_db()
    conn.execute(
        "INSERT INTO memories (content, tags, importance, agent_id) VALUES (?, ?, ?, ?)",
        (memory.content, json.dumps(memory.tags), memory.importance, memory.agent_id)
    )
    conn.commit()
    return {"status": "stored", "content": memory.content[:100]}

@app.get("/api/memories/search")
async def search_memories(q: str, limit: int = 5):
    conn = get_db()
    cursor = conn.execute(
        "SELECT content, tags, importance, created_at FROM memories "
        "WHERE content LIKE ? OR tags LIKE ? "
        "ORDER BY importance DESC, created_at DESC LIMIT ?",
        (f"%{q}%", f"%{q}%", limit)
    )
    results = [dict(row) for row in cursor.fetchall()]
    return {"query": q, "results": results, "count": len(results)}

@app.post("/api/agents")
async def create_agent(agent: AgentCreate):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO agents (name, description, capabilities, endpoint) "
        "VALUES (?, ?, ?, ?)",
        (agent.name, agent.description, json.dumps(agent.capabilities), agent.endpoint)
    )
    conn.commit()
    return {"status": "registered", "name": agent.name}

@app.get("/api/agents/search")
async def search_agents(q: str, limit: int = 10):
    conn = get_db()
    cursor = conn.execute(
        "SELECT name, description, capabilities, reputation FROM agents "
        "WHERE name LIKE ? OR description LIKE ? OR capabilities LIKE ? "
        "ORDER BY reputation DESC LIMIT ?",
        (f"%{q}%", f"%{q}%", f"%{q}%", limit)
    )
    results = [dict(row) for row in cursor.fetchall()]
    return {"query": q, "agents": results, "count": len(results)}

@app.post("/api/knowledge")
async def create_knowledge(knowledge: KnowledgeCreate):
    conn = get_db()
    conn.execute(
        "INSERT INTO knowledge (content, domain, source, confidence) VALUES (?, ?, ?, ?)",
        (knowledge.content, knowledge.domain, knowledge.source, knowledge.confidence)
    )
    conn.commit()
    return {"status": "added", "domain": knowledge.domain}

@app.get("/api/knowledge/search")
async def search_knowledge(q: str, domain: Optional[str] = None, limit: int = 10):
    conn = get_db()
    if domain:
        cursor = conn.execute(
            "SELECT content, domain, source, confidence FROM knowledge "
            "WHERE domain = ? AND content LIKE ? ORDER BY confidence DESC LIMIT ?",
            (domain, f"%{q}%", limit)
        )
    else:
        cursor = conn.execute(
            "SELECT content, domain, source, confidence FROM knowledge "
            "WHERE content LIKE ? OR domain LIKE ? ORDER BY confidence DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit)
        )
    results = [dict(row) for row in cursor.fetchall()]
    return {"query": q, "results": results, "count": len(results)}

@app.post("/api/context")
async def get_context(req: ContextRequest):
    conn = get_db()

    mem_cursor = conn.execute(
        "SELECT content, importance FROM memories "
        "WHERE content LIKE ? ORDER BY importance DESC LIMIT 5",
        (f"%{req.topic}%",)
    )
    memories = [dict(row) for row in mem_cursor.fetchall()]

    know_cursor = conn.execute(
        "SELECT content, domain, confidence FROM knowledge "
        "WHERE content LIKE ? OR domain LIKE ? ORDER BY confidence DESC LIMIT 5",
        (f"%{req.topic}%", f"%{req.topic}%")
    )
    knowledge = [dict(row) for row in know_cursor.fetchall()]

    return {
        "topic": req.topic,
        "memories": memories,
        "knowledge": knowledge,
        "summary": f"Found {len(memories)} memories and {len(knowledge)} knowledge items related to '{req.topic}'."
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
