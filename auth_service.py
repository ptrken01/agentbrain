"""
AgentBrain Auth Service — Subscription & API Key Management
Uses PostgreSQL for persistent storage
"""
import os
import json
import hashlib
import secrets
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import stripe
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/agentbrain")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="AgentBrain Auth Service")

@app.get("/")
async def root():
    return {"status": "ok", "service": "AgentBrain Auth", "version": "1.0", "database": "postgresql"}

# Database connection
def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_limits (
            tier TEXT PRIMARY KEY,
            max_memories INTEGER,
            max_api_calls_per_day INTEGER,
            features TEXT
        );
    """)
    # Insert default tiers
    cur.execute("""
        INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
        VALUES ('free', 1000, 100, '["basic_search"]')
        ON CONFLICT (tier) DO NOTHING;
    """)
    cur.execute("""
        INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
        VALUES ('pro', 50000, 10000, '["basic_search", "advanced_search", "context_packs", "agent_discovery"]')
        ON CONFLICT (tier) DO NOTHING;
    """)
    cur.execute("""
        INSERT INTO memory_limits (tier, max_memories, max_api_calls_per_day, features) 
        VALUES ('team', 999999999, 1000000, '["basic_search", "advanced_search", "context_packs", "agent_discovery", "team_brain", "marketplace", "audit_trail"]')
        ON CONFLICT (tier) DO NOTHING;
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# Models
class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key() -> str:
    return f"ab_{secrets.token_urlsafe(32)}"

def get_tier_features(tier: str) -> list:
    """Get features for a tier"""
    if tier == "free":
        return ["basic_search", "remember", "recall"]
    elif tier == "pro":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph"]
    elif tier == "team":
        return ["basic_search", "advanced_search", "remember", "recall", "context_packs", "agent_discovery", "knowledge_graph", "team_brain", "marketplace", "audit_trail"]
    return []

def get_tier_limit(user_tier: str, limit: str) -> int:
    """Get limit for a tier"""
    limits = {
        "free": {"max_memories": 1000, "max_api_calls_per_day": 100},
        "pro": {"max_memories": 50000, "max_api_calls_per_day": 10000},
        "team": {"max_memories": 999999999, "max_api_calls_per_day": 1000000}
    }
    return limits.get(user_tier, limits["free"]).get(limit, 0)

async def get_current_user(x_api_key: str = Header(...)):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE api_key = %s", (x_api_key,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user

# Routes
@app.post("/auth/register")
async def register(req: RegisterRequest):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (req.email,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")

    api_key = generate_api_key()
    password_hash = hash_password(req.password)

    cur.execute(
        "INSERT INTO users (email, password_hash, api_key) VALUES (%s, %s, %s)",
        (req.email, password_hash, api_key)
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"api_key": api_key, "tier": "free", "message": "Registration successful. Upgrade to Pro for more features."}

@app.post("/auth/login")
async def login(req: LoginRequest):
    password_hash = hash_password(req.password)
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email = %s AND password_hash = %s",
        (req.email, password_hash)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {"api_key": user["api_key"], "tier": user["tier"]}

@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "email": user["email"],
        "tier": user["tier"],
        "subscription_status": user["subscription_status"],
        "features": get_tier_features(user["tier"])
    }

@app.get("/auth/limits")
async def limits(user: dict = Depends(get_current_user)):
    tier = user["tier"]
    return {
        "tier": tier,
        "max_memories": get_tier_limit(tier, "max_memories"),
        "max_api_calls_per_day": get_tier_limit(tier, "max_api_calls_per_day"),
        "features": get_tier_features(tier)
    }

@app.post("/auth/verify")
async def verify(api_key: str = Header(...)):
    """Verify an API key and return tier info (used by MCP server)"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE api_key = %s", (api_key,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return {"valid": False, "tier": "free", "features": get_tier_features("free")}

    return {
        "valid": True,
        "tier": user["tier"],
        "features": get_tier_features(user["tier"]),
        "subscription_status": user["subscription_status"]
    }

# Stripe webhook
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_successful_payment(session)
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_update(subscription)
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await handle_subscription_cancelled(subscription)

    return {"status": "ok"}

async def handle_successful_payment(session: dict):
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    customer_email = session.get("details", {}).get("email")

    # Determine tier from price
    line_items = stripe.checkout.Session.list_line_items(session["id"])
    tier = "free"
    for item in line_items["data"]:
        price_id = item["price"]["id"]
        if price_id == os.environ.get("STRIPE_PRO_PRICE_ID", ""):
            tier = "pro"
        elif price_id == os.environ.get("STRIPE_TEAM_PRICE_ID", ""):
            tier = "team"

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (customer_email,))
    user = cur.fetchone()
    if user:
        cur.execute(
            "UPDATE users SET tier = %s, stripe_customer_id = %s, subscription_id = %s, subscription_status = %s, updated_at = NOW() WHERE id = %s",
            (tier, customer_id, subscription_id, "active", user["id"])
        )
    else:
        api_key = generate_api_key()
        cur.execute(
            "INSERT INTO users (email, api_key, tier, stripe_customer_id, subscription_id, subscription_status) VALUES (%s, %s, %s, %s, %s, %s)",
            (customer_email, api_key, tier, customer_id, subscription_id, "active")
        )
    conn.commit()
    cur.close()
    conn.close()

async def handle_subscription_update(subscription: dict):
    customer_id = subscription["customer"]
    status = subscription["status"]

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET subscription_status = %s, updated_at = NOW() WHERE stripe_customer_id = %s",
        (status, customer_id)
    )
    conn.commit()
    cur.close()
    conn.close()

async def handle_subscription_cancelled(subscription: dict):
    customer_id = subscription["customer"]

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET tier = 'free', subscription_status = 'cancelled', subscription_id = NULL, updated_at = NOW() WHERE stripe_customer_id = %s",
        (customer_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
