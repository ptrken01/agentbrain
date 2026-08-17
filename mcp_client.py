"""
AgentBrain MCP Client
Connects to the AgentBrain MCP server and tests all tools
"""
import httpx
import json
import sys

class AgentBrainMCPClient:
    """Simple MCP client for AgentBrain"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}

    def status(self):
        """Get server status"""
        r = httpx.get(f"{self.base_url}/mcp/status", timeout=15)
        return r.json()

    def remember(self, content: str, metadata: dict = None):
        """Store a memory"""
        r = httpx.post(
            f"{self.base_url}/mcp/remember",
            json={"content": content, "metadata": metadata or {}},
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def recall(self, query: str):
        """Search memories"""
        r = httpx.post(
            f"{self.base_url}/mcp/recall",
            json={"query": query},
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def register_agent(self, name: str, description: str, capabilities: list):
        """Register an agent"""
        r = httpx.post(
            f"{self.base_url}/mcp/register_agent",
            json={"name": name, "description": description, "capabilities": capabilities},
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def discover_agents(self):
        """Find agents"""
        r = httpx.get(
            f"{self.base_url}/mcp/discover_agents",
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def add_knowledge(self, content: str, relationships: list = None):
        """Add knowledge"""
        r = httpx.post(
            f"{self.base_url}/mcp/add_knowledge",
            json={"content": content, "relationships": relationships or []},
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def query_knowledge(self, query: str):
        """Query knowledge"""
        r = httpx.post(
            f"{self.base_url}/mcp/query_knowledge",
            json={"query": query},
            headers=self.headers,
            timeout=15
        )
        return r.json()

    def get_context(self, agent_id: str):
        """Get context pack"""
        r = httpx.post(
            f"{self.base_url}/mcp/get_context",
            json={"agent_id": agent_id},
            headers=self.headers,
            timeout=15
        )
        return r.json()


def main():
    import os

    # Get API key from environment or use test key
    api_key = os.environ.get("AGENTBRAIN_API_KEY", "")
    base_url = os.environ.get("AGENTBRAIN_URL", "https://agentbrain-auth.onrender.com")

    if not api_key:
        print("Error: Set AGENTBRAIN_API_KEY environment variable")
        sys.exit(1)

    client = AgentBrainMCPClient(base_url, api_key)

    print("=" * 50)
    print("  AgentBrain MCP Client")
    print("=" * 50)

    # Check server status
    print("\n1. Server Status:")
    status = client.status()
    print(f"   Status: {status.get('status')}")
    print(f"   Version: {status.get('version')}")
    print(f"   Tools: {', '.join(status.get('tools', []))}")

    # Store a memory
    print("\n2. Storing memory...")
    result = client.remember(
        "AgentBrain is the shared brain for AI agents. It provides memory, knowledge graph, and agent discovery.",
        {"source": "test", "category": "overview"}
    )
    print(f"   Memory ID: {result.get('memory_id')}")

    # Search memories
    print("\n3. Searching memories...")
    result = client.recall("AgentBrain")
    print(f"   Found {result.get('total')} memories")
    for mem in result.get('memories', []):
        print(f"   - {mem.get('content', '')[:60]}...")

    # Add knowledge
    print("\n4. Adding knowledge...")
    result = client.add_knowledge(
        "MCP (Model Context Protocol) is the standard for AI agent tools.",
        relationships=[{"type": "related", "target": "AgentBrain"}]
    )
    print(f"   Knowledge ID: {result.get('knowledge_id')}")

    # Query knowledge
    print("\n5. Querying knowledge...")
    result = client.query_knowledge("MCP")
    print(f"   Found {result.get('total')} knowledge items")

    # Register agent
    print("\n6. Registering agent...")
    result = client.register_agent(
        "TestAgent",
        "A test agent for AgentBrain",
        ["search", "remember", "recall"]
    )
    print(f"   Agent ID: {result.get('agent_id')}")

    # Discover agents
    print("\n7. Discovering agents...")
    result = client.discover_agents()
    print(f"   Found {len(result.get('agents', []))} agents")

    # Get context
    print("\n8. Getting context pack...")
    result = client.get_context("agent_123")
    print(f"   Context items: {result.get('total_context_items')}")

    print("\n" + "=" * 50)
    print("  All MCP tools working!")
    print("=" * 50)


if __name__ == "__main__":
    main()
