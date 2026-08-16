"""
AgentBrain API Server
The shared brain for AI agents — REST API + MCP.

This is the main server that powers AgentBrain. It provides:
1. REST API for web frontend and direct integration
2. MCP server for AI agent integration
3. Knowledge graph management
4. Agent registry and discovery
5. Context marketplace
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import chromadb
from chromadb.utils import embedding_functions

# --- Configuration ---
AGENTBRAIN_HOME = Path(os.getenv("AGENTBRAIN_HOME", Path.home() / ".agentbrain"))
AGENTBRAIN_HOME.mkdir(parents=True, exist_ok=True)

CHROMA_PATH = AGENTBRAIN_HOME / "chroma"

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

# --- FastAPI App ---
app = FastAPI(
    title="AgentBrain API",
    description="The shared brain for AI agents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---
class MemoryCreate(BaseModel):
    content: str
    tags: List[str] = []
    agent_id: str = "anonymous"
    importance: float = 0.5


class AgentRegister(BaseModel):
    name: str
    description: str
    capabilities: List[str]
    endpoint: str = ""


class KnowledgeCreate(BaseModel):
    content: str
    domain: str = "general"
    source: str = "unknown"
    confidence: float = 0.8


class ContextPackCreate(BaseModel):
    title: str
    description: str
    domain: str
    content: str
    price: float = 0.0
    tags: List[str] = []


class AgentHireRequest(BaseModel):
    agent_id: str
    task: str
    budget: float = 0.0


# --- API Endpoints ---

@app.get("/")
async def root():
    return {
        "name": "AgentBrain",
        "version": "0.1.0",
        "description": "The shared brain for AI agents",
        "status": "running",
        "endpoints": {
            "memories": "/memories",
            "agents": "/agents",
            "knowledge": "/knowledge",
            "context": "/context/{topic}",
            "marketplace": "/marketplace",
        }
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "collections": {
            "memories": memories_collection.count(),
            "agents": agents_collection.count(),
            "knowledge": knowledge_collection.count(),
        }
    }


# --- Memories ---

@app.post("/memories")
async def store_memory(memory: MemoryCreate):
    """Store a memory in the shared brain."""
    memory_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(memory.content) % 10000:04d}"

    memories_collection.add(
        documents=[memory.content],
        ids=[memory_id],
        metadatas=[{
            "tags": ",".join(memory.tags),
            "agent_id": memory.agent_id,
            "importance": memory.importance,
            "created_at": datetime.now().isoformat(),
        }]
    )

    return {"status": "stored", "memory_id": memory_id}


@app.get("/memories/search")
async def search_memories(
    q: str = Query(..., description="Search query"),
    limit: int = Query(5, ge=1, le=50),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
):
    """Search memories by semantic similarity."""
    where = {}
    if tags:
        tag_list = tags.split(",")
        where = {"tags": {"$in": tag_list}}

    results = memories_collection.query(
        query_texts=[q],
        n_results=limit,
        where=where if where else None
    )

    memories = []
    if results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            memories.append({
                "id": results["ids"][0][i],
                "content": doc,
                "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
                "agent_id": meta.get("agent_id", "unknown"),
                "importance": meta.get("importance", 0.5),
                "created_at": meta.get("created_at", ""),
            })

    return {"count": len(memories), "memories": memories}


# --- Agents ---

@app.post("/agents")
async def register_agent(agent: AgentRegister):
    """Register an agent in the registry."""
    agent_id = f"agent_{agent.name.lower().replace(' ', '_')}_{hash(agent.description) % 10000:04d}"

    agents_collection.add(
        documents=[f"{agent.name}. {agent.description}. Capabilities: {', '.join(agent.capabilities)}"],
        ids=[agent_id],
        metadatas=[{
            "name": agent.name,
            "description": agent.description,
            "capabilities": ",".join(agent.capabilities),
            "endpoint": agent.endpoint,
            "registered_at": datetime.now().isoformat(),
            "reputation": 0.5,
        }]
    )

    return {"status": "registered", "agent_id": agent_id}


@app.get("/agents/search")
async def search_agents(
    q: str = Query(..., description="Search query"),
    limit: int = Query(5, ge=1, le=50),
):
    """Find agents by capability or description."""
    results = agents_collection.query(
        query_texts=[q],
        n_results=limit
    )

    agents = []
    if results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            agents.append({
                "id": results["ids"][0][i],
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                "capabilities": meta.get("capabilities", "").split(",") if meta.get("capabilities") else [],
                "endpoint": meta.get("endpoint", ""),
                "reputation": meta.get("reputation", 0.5),
            })

    return {"count": len(agents), "agents": agents}


# --- Knowledge ---

@app.post("/knowledge")
async def add_knowledge(knowledge: KnowledgeCreate):
    """Add structured knowledge to the shared brain."""
    knowledge_id = f"knw_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(knowledge.content) % 10000:04d}"

    knowledge_collection.add(
        documents=[knowledge.content],
        ids=[knowledge_id],
        metadatas=[{
            "domain": knowledge.domain,
            "source": knowledge.source,
            "confidence": knowledge.confidence,
            "created_at": datetime.now().isoformat(),
        }]
    )

    return {"status": "stored", "knowledge_id": knowledge_id}


@app.get("/knowledge/search")
async def search_knowledge(
    q: str = Query(..., description="Search query"),
    domain: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=50),
):
    """Query the knowledge graph."""
    where = {}
    if domain:
        where = {"domain": domain}

    results = knowledge_collection.query(
        query_texts=[q],
        n_results=limit,
        where=where if where else None
    )

    items = []
    if results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            items.append({
                "id": results["ids"][0][i],
                "content": doc,
                "domain": meta.get("domain", "general"),
                "source": meta.get("source", "unknown"),
                "confidence": meta.get("confidence", 0.8),
            })

    return {"count": len(items), "knowledge": items}


# --- Context (combined view) ---

@app.get("/context/{topic}")
async def get_context(topic: str, limit: int = Query(3, ge=1, le=20)):
    """Get rich context about a topic — combines memories, knowledge, and agents."""
    mem_results = memories_collection.query(query_texts=[topic], n_results=limit)
    knw_results = knowledge_collection.query(query_texts=[topic], n_results=limit)
    agt_results = agents_collection.query(query_texts=[topic], n_results=limit)

    context = {
        "topic": topic,
        "memories": [
            {"content": doc, "metadata": meta}
            for doc, meta in zip(mem_results["documents"][0], mem_results["metadatas"][0])
        ] if mem_results.get("documents") else [],
        "knowledge": [
            {"content": doc, "metadata": meta}
            for doc, meta in zip(knw_results["documents"][0], knw_results["metadatas"][0])
        ] if knw_results.get("documents") else [],
        "relevant_agents": [
            {"name": meta.get("name"), "description": meta.get("description")}
            for doc, meta in zip(agt_results["documents"][0], agt_results["metadatas"][0])
        ] if agt_results.get("documents") else [],
    }

    return context


# --- Marketplace ---

@app.get("/marketplace")
async def list_marketplace():
    """List available context packs and agent services."""
    # For now, return a placeholder
    return {
        "packs": [],
        "agents": [],
        "message": "Marketplace coming soon — be the first to list!"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
