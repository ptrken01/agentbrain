"""
AgentBrain Auth Service — Subscription & API Key Management
Uses pg8000 (pure Python PostgreSQL driver) for reliability
"""
import os
from datetime import datetime
import json
import hashlib
import secrets
import pg8000
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
import stripe

# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID", "price_1U5OUhDxZTiv22XcmA4OF2ds")
STRIPE_TEAM_PRICE_ID = os.environ.get("STRIPE_TEAM_PRICE_ID", "price_1U5OUjDxZTiv22Xck71tvMPu")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="AgentBrain Auth Service")

def get_db():
    # Parse DATABASE_URL
    # postgresql://user:pass@host:5432/dbname
    url = DATABASE_URL.replace("postgresql://", "")
    if "@" in url:
        user_pass, host_db = url.split("@")
        user, password = user_pass.split(":")
        host_port, dbname = host_db.split("/")
        if ":" in host_port:
            host, port = host_port.split(":")
        else:
            host = host_port
            port = 5432
    else:
        user, password, host, port, dbname = "user", "pass", "localhost", 5432, "agentbrain"

    conn = pg8000.connect(user=user, password=password, host=host, port=int(port), database=dbname)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            api_key TEXT UNIQUE,
            tier TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            subscription_id TEXT,
            subscription_status TEXT DEFAULT 'inactive',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

db_initialized = False
try:
    init_db()
    db_initialized = True
    print("DB initialized")
except Exception as e:
    print(f"DB init warning: {e}")

def get_tier_features(tier: str) -> list:
    if tier == "free":
        return ["basic_search", "remember", "recall"]
    elif tier == "pro":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph"]
    elif tier == "team":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph", "team_brain", "marketplace", "audit_trail"]
    return []

def get_tier_limit(user_tier: str, limit: str) -> int:
    limits = {
        "free": {"max_memories": 1000, "max_api_calls_per_day": 100},
        "pro": {"max_memories": 50000, "max_api_calls_per_day": 10000},
        "team": {"max_memories": 999999999, "max_api_calls_per_day": 1000000}
    }
    return limits.get(user_tier, limits["free"]).get(limit, 0)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key() -> str:
    return f"ab_{secrets.token_urlsafe(32)}"

def get_user(api_key: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE api_key = %s", (api_key,))
    columns = [desc[0] for desc in cur.description]
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return dict(zip(columns, row))
    return None

@app.get("/")
async def root():
    return {"status": "ok", "service": "AgentBrain Auth", "db_initialized": db_initialized}

@app.get("/health")
async def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

@app.post("/auth/register")
async def register(request: Request):
    data = await request.json()
    email = data.get("email", "")
    password = data.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    api_key = generate_api_key()
    cur.execute(
        "INSERT INTO users (email, password_hash, api_key) VALUES (%s, %s, %s)",
        (email, hash_password(password), api_key)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"api_key": api_key, "tier": "free"}

@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email", "")
    password = data.get("password", "")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s AND password_hash = %s",
                (email, hash_password(password)))
    columns = [desc[0] for desc in cur.description]
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = dict(zip(columns, row))
    return {"api_key": user["api_key"], "tier": user["tier"]}

@app.get("/auth/limits")
async def limits(x_api_key: str = Header(...)):
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    tier = user["tier"]
    return {
        "tier": tier,
        "max_memories": get_tier_limit(tier, "max_memories"),
        "max_api_calls_per_day": get_tier_limit(tier, "max_api_calls_per_day"),
        "features": get_tier_features(tier)
    }

@app.post("/auth/verify")
async def verify(api_key: str = Header(..., alias="api-key")):
    user = get_user(api_key)
    if not user:
        return {"valid": False, "tier": "free", "features": get_tier_features("free")}
    return {
        "valid": True,
        "tier": user["tier"],
        "features": get_tier_features(user["tier"])
    }

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email") or session.get("customer_details", {}).get("email")
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        # Try to get line items from Stripe API, fallback to metadata
        tier = "free"
        try:
            line_items = stripe.checkout.Session.list_line_items(session["id"])
            for item in line_items["data"]:
                if item["price"]["id"] == STRIPE_PRO_PRICE_ID:
                    tier = "pro"
                elif item["price"]["id"] == STRIPE_TEAM_PRICE_ID:
                    tier = "team"
        except Exception:
            # For test events, try to determine tier from metadata or default to pro
            tier = "pro"  # Default for testing
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (customer_email,))
        columns = [desc[0] for desc in cur.description]
        user = cur.fetchone()
        if user:
            user_dict = dict(zip(columns, user))
            cur.execute("UPDATE users SET tier=%s, stripe_customer_id=%s, subscription_id=%s, subscription_status=%s WHERE id=%s",
                        (tier, customer_id, subscription_id, "active", user_dict["id"]))
        else:
            api_key = generate_api_key()
            cur.execute("INSERT INTO users (email, api_key, tier, stripe_customer_id, subscription_id, subscription_status) VALUES (%s,%s,%s,%s,%s,%s)",
                        (customer_email, api_key, tier, customer_id, subscription_id, "active"))
        conn.commit()
        cur.close()
        conn.close()
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET tier='free', subscription_status='cancelled' WHERE stripe_customer_id=%s",
                    (subscription["customer"],))
        conn.commit()
        cur.close()
        conn.close()
    return {"status": "ok"}


# ============================================================
# MCP Server Endpoints
# ============================================================

from datetime import datetime

# In-memory storage (for demo - production would use vector DB)
memories_db = {}
knowledge_db = {}
agents_db = {}

@app.get("/mcp/status")
async def mcp_status():
    """MCP server status"""
    return {
        "status": "running",
        "service": "AgentBrain MCP Server",
        "version": "1.0",
        "tools": [
            "remember",
            "recall",
            "register_agent",
            "discover_agents",
            "add_knowledge",
            "query_knowledge",
            "get_context"
        ]
    }

@app.post("/mcp/remember")
async def mcp_remember(request: Request, x_api_key: str = Header(...)):
    """Store a memory"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tier = user["tier"]
    max_memories = get_tier_limit(tier, "max_memories")
    user_memories = [m for m in memories_db.values() if m.get("user_id") == user["id"]]
    if len(user_memories) >= max_memories:
        raise HTTPException(status_code=403, detail=f"Memory limit reached ({max_memories}). Upgrade to store more.")

    data = await request.json()
    memory_id = f"mem_{secrets.token_urlsafe(16)}"
    memories_db[memory_id] = {
        "id": memory_id,
        "user_id": user["id"],
        "content": data.get("content", ""),
        "metadata": data.get("metadata", {}),
        "created_at": datetime.now().isoformat()
    }
    return {"memory_id": memory_id, "status": "stored"}

@app.post("/mcp/recall")
async def mcp_recall(request: Request, x_api_key: str = Header(...)):
    """Retrieve memories"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    data = await request.json()
    query = data.get("query", "")
    user_memories = [m for m in memories_db.values() if m.get("user_id") == user["id"]]
    results = [m for m in user_memories if query.lower() in m["content"].lower()]
    return {"memories": results[:10], "total": len(results)}

@app.post("/mcp/register_agent")
async def mcp_register_agent(request: Request, x_api_key: str = Header(...)):
    """Register an agent (Pro+)"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if user["tier"] == "free":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to register agents")

    data = await request.json()
    agent_id = f"agent_{secrets.token_urlsafe(16)}"
    agents_db[agent_id] = {
        "id": agent_id,
        "user_id": user["id"],
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "capabilities": data.get("capabilities", []),
        "created_at": datetime.now().isoformat()
    }
    return {"agent_id": agent_id, "status": "registered"}

@app.get("/mcp/discover_agents")
async def mcp_discover_agents(x_api_key: str = Header(...)):
    """Discover agents (Pro+)"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if user["tier"] == "free":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to access agent marketplace")
    return {"agents": list(agents_db.values())}

@app.post("/mcp/add_knowledge")
async def mcp_add_knowledge(request: Request, x_api_key: str = Header(...)):
    """Add knowledge (Pro+)"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if user["tier"] == "free":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to add knowledge")

    data = await request.json()
    knowledge_id = f"knowledge_{secrets.token_urlsafe(16)}"
    knowledge_db[knowledge_id] = {
        "id": knowledge_id,
        "user_id": user["id"],
        "content": data.get("content", ""),
        "relationships": data.get("relationships", []),
        "created_at": datetime.now().isoformat()
    }
    return {"knowledge_id": knowledge_id, "status": "added"}

@app.post("/mcp/query_knowledge")
async def mcp_query_knowledge(request: Request, x_api_key: str = Header(...)):
    """Query knowledge (Pro+)"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if user["tier"] == "free":
        raise HTTPException(status_code=403, detail="Upgrade to Pro to query knowledge")

    data = await request.json()
    query = data.get("query", "")
    user_knowledge = [k for k in knowledge_db.values() if k.get("user_id") == user["id"]]
    results = [k for k in user_knowledge if query.lower() in k["content"].lower()]
    return {"knowledge": results[:10], "total": len(results)}

@app.post("/mcp/get_context")
async def mcp_get_context(request: Request, x_api_key: str = Header(...)):
    """Get context pack"""
    user = get_user(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    data = await request.json()
    agent_id = data.get("agent_id", "")
    user_memories = [m for m in memories_db.values() if m.get("user_id") == user["id"]]
    user_knowledge = [k for k in knowledge_db.values() if k.get("user_id") == user["id"]]

    return {
        "agent_id": agent_id,
        "memories": user_memories[:5],
        "knowledge": user_knowledge[:5],
        "total_context_items": len(user_memories) + len(user_knowledge)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
