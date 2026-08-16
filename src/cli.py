"""AgentBrain CLI"""

import argparse
import sys
import os
from pathlib import Path


def serve_mcp():
    """Run the MCP server."""
    from agentbrain.server import main as mcp_main
    import asyncio
    asyncio.run(mcp_main())


def serve_api(host: str = "0.0.0.0", port: int = 8000):
    """Run the REST API server."""
    import uvicorn
    from agentbrain.api import app
    uvicorn.run(app, host=host, port=port)


def init():
    """Initialize AgentBrain."""
    home = Path(os.getenv("AGENTBRAIN_HOME", Path.home() / ".agentbrain"))
    home.mkdir(parents=True, exist_ok=True)
    print(f"✅ AgentBrain initialized at {home}")
    print(f"   ChromaDB: {home / 'chroma'}")
    print(f"   Database: {home / 'agentbrain.db'}")


def status():
    """Show AgentBrain status."""
    import chromadb
    home = Path(os.getenv("AGENTBRAIN_HOME", Path.home() / ".agentbrain"))
    chroma_path = home / "chroma"

    if not chroma_path.exists():
        print("❌ AgentBrain not initialized. Run: agentbrain init")
        return

    client = chromadb.PersistentClient(path=str(chroma_path))
    collections = client.list_collections()

    print("🧠 AgentBrain Status")
    print("=" * 40)
    for col in collections:
        print(f"  {col.name}: {col.count()} items")


def main():
    parser = argparse.ArgumentParser(description="AgentBrain - The Shared Brain for AI Agents")
    subparsers = parser.add_subparsers(dest="command")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the server")
    serve_parser.add_argument("--mode", choices=["mcp", "api", "both"], default="both")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)

    # init command
    subparsers.add_parser("init", help="Initialize AgentBrain")

    # status command
    subparsers.add_parser("status", help="Show status")

    args = parser.parse_args()

    if args.command == "serve":
        if args.mode == "mcp":
            serve_mcp()
        elif args.command == "api":
            serve_api(args.host, args.port)
        else:
            serve_api(args.host, args.port)
    elif args.command == "init":
        init()
    elif args.command == "status":
        status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
